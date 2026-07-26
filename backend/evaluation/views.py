"""Evaluation API — locked outer-test metrics + model card."""

from __future__ import annotations

import json
import os
import pickle

import numpy as np
from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from evaluation.eval_utils import build_model_card, evaluate_binary, feature_psi_report
from modeling.calibration_utils import apply_calibrator, load_calibrator
from modeling.lineage import load_lineage
from modeling.booster_adapters import load_adapter_from_path


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

            algo = (
                model_info.get('algorithm')
                or train_data.get('algorithm')
                or (model_info.get('model_type') or 'xgboost').replace('_classifier', '')
            )
            adapter = load_adapter_from_path(
                model_abs,
                algorithm=algo,
                feature_names=list(map(str, X_test.columns)),
                cat_features=list(model_info.get('categorical_features_used') or []),
            )
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

            # Also surface valid metrics from modeling for comparison
            evaluation['comparison'] = {
                'valid_auc': model_info.get('valid_auc'),
                'modeling_test_auc': model_info.get('test_auc'),
                'modeling_test_auc_calibrated': model_info.get('test_auc_calibrated'),
                'evaluation_test_auc': evaluation['metrics'].get('roc_auc'),
            }

            lineage = load_lineage(file_id)
            card = build_model_card(file_id, evaluation, lineage=lineage, modeling_status=modeling_status)

            out_dir = os.path.join(settings.MEDIA_ROOT, 'evaluation')
            os.makedirs(out_dir, exist_ok=True)
            eval_path = os.path.join(out_dir, f'{file_id}_evaluation.json')
            card_path = os.path.join(out_dir, f'{file_id}_model_card.json')
            payload = {
                'status': 'ok',
                'file_id': file_id,
                'evaluation': evaluation,
                'model_card': card,
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
                step_order = {
                    'declaration': 0, 'preprocessing': 1, 'data_quality': 2,
                    'modeling': 3, 'sfs': 4, 'evaluation': 5, 'deployment': 6,
                }
                run = PipelineRun.objects.filter(file_id=file_id).order_by('-updated_at').first()
                if run is not None:
                    st = dict(run.state or {})
                    st['evaluation'] = {
                        'evaluation_path': payload['evaluation_path'],
                        'model_card_path': payload['model_card_path'],
                        'metrics': evaluation.get('metrics'),
                        'lineage_id': card.get('lineage_id'),
                    }
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
