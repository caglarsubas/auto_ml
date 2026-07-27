"""Evaluation API — locked outer-test metrics + model card."""

from __future__ import annotations

import io
import json
import os
import pickle
import zipfile
from datetime import datetime, timezone

import numpy as np
from django.conf import settings
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from evaluation.eval_utils import (
    build_model_card, evaluate_binary, evaluate_regression, feature_psi_report,
)
from modeling.calibration_utils import apply_calibrator, load_calibrator
from modeling.crisp_dm import (
    expected_cost_table,
    merge_crisp_dm,
    normalize_business_understanding,
    recommend_threshold_by_cost,
)
from modeling.lineage import load_lineage
from modeling.booster_adapters import load_adapter_from_path


def _load_bu_from_request_or_run(data: dict, file_id: int):
    bu = normalize_business_understanding(data.get('business_understanding'))
    gov = data.get('governance_checks') if isinstance(data.get('governance_checks'), dict) else {}
    try:
        from modeling.models import PipelineRun
        run = None
        run_id = data.get('pipeline_run_id')
        if run_id:
            run = PipelineRun.objects.filter(pk=int(run_id)).first()
        if run is None:
            run = PipelineRun.objects.filter(file_id=file_id).order_by('-updated_at').first()
        if run is not None:
            st = run.state or {}
            crisp = merge_crisp_dm(st.get('crisp_dm'), {
                'business_understanding': st.get('business_understanding') or bu,
            })
            bu = crisp['business_understanding']
            if not gov:
                gov = crisp.get('governance_checks') or {}
    except Exception:
        pass
    return bu, gov


def _resolve_algorithm(model_info: dict, train_data: dict) -> str:
    raw = (
        model_info.get('algorithm')
        or train_data.get('algorithm')
        or (model_info.get('model_type') or 'xgboost')
    )
    algo = str(raw).replace('_classifier', '').replace('_regressor', '')
    return algo or 'xgboost'


def _is_regression_task(model_info: dict, train_data: dict) -> bool:
    task = (train_data.get('task') or model_info.get('task') or '').strip().lower()
    if task == 'regression':
        return True
    mt = str(model_info.get('model_type') or '')
    mp = str(model_info.get('model_path') or train_data.get('model_path') or '')
    return 'regressor' in mt.lower() or 'regressor' in mp.lower()


def _load_modeling_status(file_id: int):
    path = os.path.join(settings.MEDIA_ROOT, 'modeling', f'{file_id}_status.json')
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


@method_decorator(csrf_exempt, name='dispatch')
class EvaluationRunView(APIView):
    """Score the locked outer test set and persist evaluation + model card.

    Payload: { file_id: int, threshold?: float = 0.5, features?: [str] }
    """

    def post(self, request, *args, **kwargs):
        data = request.data or {}
        file_id = data.get('file_id')
        if file_id is None:
            return Response({'error': 'file_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            file_id = int(file_id)
        except Exception:
            return Response({'error': 'file_id must be an integer'}, status=status.HTTP_400_BAD_REQUEST)

        threshold = float(data.get('threshold', 0.5))
        features = data.get('features')
        bu, gov = _load_bu_from_request_or_run(data, file_id)

        train_data_path = os.path.join(settings.MEDIA_ROOT, 'train_data', f'{file_id}_train_data.pkl')
        if not os.path.exists(train_data_path):
            return Response({
                'error': 'Training data not found. Run modeling first.',
            }, status=status.HTTP_404_NOT_FOUND)

        modeling_status = _load_modeling_status(file_id) or {}
        model_info = modeling_status.get('model') or {}
        model_rel = model_info.get('model_path') or f'models/{file_id}_xgb_classifier.json'
        model_abs = os.path.join(settings.MEDIA_ROOT, model_rel) if not os.path.isabs(model_rel) else model_rel
        if not os.path.exists(model_abs):
            return Response({'error': f'Model artifact not found: {model_rel}'}, status=status.HTTP_404_NOT_FOUND)

        try:
            with open(train_data_path, 'rb') as f:
                train_data = pickle.load(f)
            X_test = train_data.get('X_test')
            y_test = train_data.get('y_test')
            if X_test is None or y_test is None or len(X_test) == 0:
                return Response({
                    'error': 'Locked outer test set missing from train_data. Re-run modeling.',
                }, status=status.HTTP_409_CONFLICT)

            if features:
                valid = [c for c in features if c in X_test.columns]
                if valid:
                    X_test = X_test[valid]

            # Prefer hyperparam-selected features when present and no override
            if not features:
                hp_path = os.path.join(settings.MEDIA_ROOT, 'hyperparam_results', f'{file_id}_hyperparam.json')
                if os.path.exists(hp_path):
                    try:
                        with open(hp_path, 'r', encoding='utf-8') as hf:
                            hp = json.load(hf)
                        hp_feats = hp.get('features') or []
                        valid = [c for c in hp_feats if c in X_test.columns]
                        if valid:
                            X_test = X_test[valid]
                    except Exception:
                        pass

            algo = _resolve_algorithm(model_info, train_data)
            is_regression = _is_regression_task(model_info, train_data)
            adapter = load_adapter_from_path(
                model_abs,
                algorithm=algo,
                feature_names=list(map(str, X_test.columns)),
                cat_features=list(model_info.get('categorical_features_used') or []),
            )

            if is_regression:
                y_pred = np.asarray(adapter.predict(X_test), dtype=float).ravel()
                evaluation = evaluate_regression(y_test, y_pred)
                evaluation['scores_calibrated'] = False
                evaluation['calibration'] = {'applied': False, 'fitted': False}
                evaluation['comparison'] = {
                    'valid_r2': model_info.get('valid_r2'),
                    'modeling_test_r2': model_info.get('test_r2'),
                    'modeling_test_rmse': model_info.get('test_rmse'),
                    'evaluation_test_r2': evaluation['metrics'].get('r2'),
                    'evaluation_test_rmse': evaluation['metrics'].get('rmse'),
                }
            else:
                y_proba_raw = np.asarray(adapter.predict_proba(X_test), dtype=float).ravel()
                y_proba = y_proba_raw
                calibration_meta = (
                    train_data.get('calibration')
                    or model_info.get('calibration')
                    or {}
                )
                calibrator_rel = (
                    train_data.get('calibrator_path')
                    or model_info.get('calibrator_path')
                )
                if calibrator_rel and calibration_meta.get('fitted'):
                    try:
                        calibrator = load_calibrator(calibrator_rel, settings.MEDIA_ROOT)
                        y_proba = apply_calibrator(calibrator, y_proba_raw)
                        evaluation_calibration = {
                            **calibration_meta,
                            'applied': True,
                            'calibrator_path': calibrator_rel,
                        }
                    except Exception as cal_err:
                        evaluation_calibration = {
                            **calibration_meta,
                            'applied': False,
                            'warning': f'Calibrator load failed: {cal_err}',
                        }
                else:
                    evaluation_calibration = {
                        **calibration_meta,
                        'applied': False,
                    }

                evaluation = evaluate_binary(y_test, y_proba, threshold=threshold)
                evaluation['scores_calibrated'] = bool(evaluation_calibration.get('applied'))
                evaluation['calibration'] = evaluation_calibration
                if evaluation_calibration.get('applied'):
                    try:
                        raw_eval = evaluate_binary(y_test, y_proba_raw, threshold=threshold)
                        evaluation['metrics_raw'] = raw_eval.get('metrics')
                    except Exception:
                        pass
                evaluation['comparison'] = {
                    'valid_auc': model_info.get('valid_auc'),
                    'modeling_test_auc': model_info.get('test_auc'),
                    'modeling_test_auc_calibrated': model_info.get('test_auc_calibrated'),
                    'evaluation_test_auc': evaluation['metrics'].get('roc_auc'),
                }
                # Business-cost table from BU cost matrix
                cm = (bu.get('success_criteria') or {}).get('cost_matrix') or {}
                thr_rows = evaluation.get('threshold_table') or []
                # Attach confusion counts for cost when available via recompute
                enriched_thr = []
                for row in thr_rows:
                    r = dict(row)
                    try:
                        thr = float(r.get('threshold'))
                        y_hat = (y_proba >= thr).astype(int)
                        from sklearn.metrics import confusion_matrix
                        tn, fp, fn, tp = confusion_matrix(
                            np.asarray(y_test).astype(int), y_hat, labels=[0, 1],
                        ).ravel()
                        r['tn'], r['fp'], r['fn'], r['tp'] = int(tn), int(fp), int(fn), int(tp)
                    except Exception:
                        pass
                    enriched_thr.append(r)
                cost_rows = expected_cost_table(
                    enriched_thr,
                    fn_cost=float(cm.get('fn_cost', 1.0)),
                    fp_cost=float(cm.get('fp_cost', 1.0)),
                )
                evaluation['threshold_table'] = cost_rows
                evaluation['recommended_threshold'] = recommend_threshold_by_cost(cost_rows)

            evaluation['split'] = train_data.get('split_meta') or model_info.get('split') or {}
            evaluation['n_test'] = int(len(y_test))
            evaluation['feature_count'] = int(X_test.shape[1])
            evaluation['model_path'] = model_rel
            evaluation['algorithm'] = algo
            evaluation['holdout'] = 'outer_test'
            evaluation['leakage_scan'] = model_info.get('leakage_scan')
            try:
                X_train = train_data.get('X_train')
                if X_train is not None:
                    evaluation['psi_vs_train'] = feature_psi_report(
                        X_train[X_test.columns], X_test, top_n=25,
                    )
            except Exception as psi_err:
                evaluation['psi_vs_train'] = {'error': str(psi_err)}

            lineage = load_lineage(file_id)
            card = build_model_card(
                file_id, evaluation,
                lineage=lineage,
                modeling_status=modeling_status,
                business_understanding=bu,
                governance_checks=gov,
            )

            out_dir = os.path.join(settings.MEDIA_ROOT, 'evaluation')
            os.makedirs(out_dir, exist_ok=True)
            eval_path = os.path.join(out_dir, f'{file_id}_evaluation.json')
            card_path = os.path.join(out_dir, f'{file_id}_model_card.json')
            payload = {
                'status': 'ok',
                'file_id': file_id,
                'evaluation': evaluation,
                'model_card': card,
                'success_criteria_result': card.get('success_criteria_result'),
                'evaluation_path': os.path.relpath(eval_path, settings.MEDIA_ROOT),
                'model_card_path': os.path.relpath(card_path, settings.MEDIA_ROOT),
            }
            with open(eval_path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2, default=str)
            with open(card_path, 'w', encoding='utf-8') as f:
                json.dump(card, f, indent=2, default=str)

            # Attach lineage pointer onto PipelineRun state when possible
            try:
                from modeling.models import PipelineRun
                from modeling.crisp_dm import merge_crisp_dm
                step_order = {
                    'declaration': 0, 'preprocessing': 1, 'data_quality': 2,
                    'modeling': 3, 'sfs': 4, 'evaluation': 5, 'deployment': 6,
                    'monitoring': 7,
                }
                run = PipelineRun.objects.filter(file_id=file_id).order_by('-updated_at').first()
                if run is not None:
                    st = dict(run.state or {})
                    st['evaluation'] = {
                        'evaluation_path': payload['evaluation_path'],
                        'model_card_path': payload['model_card_path'],
                        'metrics': evaluation.get('metrics'),
                        'lineage_id': card.get('lineage_id'),
                        'deploy_ready': card.get('deploy_ready'),
                        'deployment_readiness': (card.get('sections') or {}).get('deployment_readiness'),
                        'success_criteria_result': card.get('success_criteria_result'),
                    }
                    st['crisp_dm'] = merge_crisp_dm(st.get('crisp_dm'), {
                        'business_understanding': bu,
                        'governance_checks': gov,
                        'phase_status': {'evaluation': 'completed'},
                    })
                    if lineage:
                        st['lineage'] = {
                            'lineage_id': lineage.get('lineage_id'),
                            'path': f'lineage/{file_id}_lineage.json',
                        }
                    cur = run.current_step or 'modeling'
                    if step_order.get('evaluation', 5) >= step_order.get(cur, 0):
                        run.current_step = 'evaluation'
                    run.state = st
                    run.save(update_fields=['current_step', 'state', 'updated_at'])
            except Exception as pe:
                print(f"[Evaluation] PipelineRun update skipped: {pe}")

            return Response(payload, status=status.HTTP_200_OK)
        except Exception as e:
            import traceback
            print("[Evaluation] ERROR:\n" + traceback.format_exc())
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class EvaluationStatusView(APIView):
    def get(self, request, file_id: int, *args, **kwargs):
        path = os.path.join(settings.MEDIA_ROOT, 'evaluation', f'{file_id}_evaluation.json')
        if not os.path.exists(path):
            return Response({'status': 'unknown', 'file_id': file_id}, status=status.HTTP_200_OK)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return Response(json.load(f), status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'status': 'error', 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class EvaluationPackView(APIView):
    """Download evaluation pack zip (metrics + model card + SHAP snapshot)."""

    def post(self, request, *args, **kwargs):
        data = request.data or {}
        file_id = data.get('file_id')
        if file_id is None:
            return Response({'error': 'file_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            file_id = int(file_id)
        except Exception:
            return Response({'error': 'file_id must be an integer'}, status=status.HTTP_400_BAD_REQUEST)

        eval_path = os.path.join(settings.MEDIA_ROOT, 'evaluation', f'{file_id}_evaluation.json')
        card_path = os.path.join(settings.MEDIA_ROOT, 'evaluation', f'{file_id}_model_card.json')
        if not os.path.exists(eval_path):
            return Response({'error': 'Evaluation not found. Run evaluation first.'}, status=status.HTTP_404_NOT_FOUND)

        buf = io.BytesIO()
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        name = f'evaluation_pack_{file_id}_{stamp}.zip'
        with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(eval_path, 'evaluation.json')
            if os.path.exists(card_path):
                zf.write(card_path, 'model_card.json')
            shap_candidates = [
                os.path.join(settings.MEDIA_ROOT, 'modeling', f'{file_id}_status.json'),
                os.path.join(settings.MEDIA_ROOT, 'explainability', f'{file_id}_shap.json'),
            ]
            for p in shap_candidates:
                if os.path.exists(p):
                    zf.write(p, os.path.basename(p))
            zf.writestr(
                'README.txt',
                f'DeclarAI evaluation pack\nfile_id={file_id}\ngenerated_utc={stamp}\n',
            )
        raw = buf.getvalue()
        out_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, name), 'wb') as f:
            f.write(raw)
        resp = HttpResponse(raw, content_type='application/zip')
        resp['Content-Disposition'] = f'attachment; filename="{name}"'
        return resp


@method_decorator(csrf_exempt, name='dispatch')
class GovernanceChecksView(APIView):
    """Persist interactive governance checkboxes onto pipeline crisp_dm + model card."""

    def post(self, request, *args, **kwargs):
        data = request.data or {}
        file_id = data.get('file_id')
        checks = data.get('checks') if isinstance(data.get('checks'), dict) else {}
        if file_id is None:
            return Response({'error': 'file_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            file_id = int(file_id)
        except Exception:
            return Response({'error': 'file_id must be an integer'}, status=status.HTTP_400_BAD_REQUEST)

        from modeling.models import PipelineRun
        from modeling.crisp_dm import merge_crisp_dm

        run = PipelineRun.objects.filter(file_id=file_id).order_by('-updated_at').first()
        if run is not None:
            st = dict(run.state or {})
            st['crisp_dm'] = merge_crisp_dm(st.get('crisp_dm'), {'governance_checks': checks})
            run.state = st
            run.save(update_fields=['state', 'updated_at'])

        card_path = os.path.join(settings.MEDIA_ROOT, 'evaluation', f'{file_id}_model_card.json')
        if os.path.exists(card_path):
            try:
                with open(card_path, 'r', encoding='utf-8') as f:
                    card = json.load(f)
                card['governance_checks'] = checks
                with open(card_path, 'w', encoding='utf-8') as f:
                    json.dump(card, f, indent=2, default=str)
            except Exception:
                pass

        eval_path = os.path.join(settings.MEDIA_ROOT, 'evaluation', f'{file_id}_evaluation.json')
        if os.path.exists(eval_path):
            try:
                with open(eval_path, 'r', encoding='utf-8') as f:
                    payload = json.load(f)
                if isinstance(payload.get('model_card'), dict):
                    payload['model_card']['governance_checks'] = checks
                with open(eval_path, 'w', encoding='utf-8') as f:
                    json.dump(payload, f, indent=2, default=str)
            except Exception:
                pass

        return Response({'status': 'ok', 'file_id': file_id, 'checks': checks})
