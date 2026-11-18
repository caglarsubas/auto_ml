"""API views for CRISP-DM export pack, monitoring, and iteration clone."""

from __future__ import annotations

import io
import json
import os
import pickle
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from access_control.storage import managed_path
from modeling.crisp_dm import (
    build_crisp_export_zip,
    compute_monitoring_report,
    sequential_pattern_evidence,
    enrich_datq_with_recommendations,
    merge_crisp_dm,
    normalize_business_understanding,
)
from deployment.evidence import execution_artifact
from modeling.diagnostics import DIAGNOSTIC_LIMITATIONS
from modeling.execution_artifacts import execution_root, load_execution
from modeling.models import PipelineRun
from preprocessing.stage_publication import StageConflict, read_datq


@method_decorator(csrf_exempt, name='dispatch')
class CrispExportPackView(APIView):
    """GET/POST → zip audit pack for file_id (+ optional pipeline crisp_dm)."""

    def post(self, request, *args, **kwargs):
        data = request.data or {}
        file_id = data.get('file_id')
        if file_id is None:
            return Response({'error': 'file_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            file_id = int(file_id)
        except Exception:
            return Response({'error': 'file_id must be an integer'}, status=status.HTTP_400_BAD_REQUEST)

        bu = normalize_business_understanding(data.get('business_understanding'))
        crisp = merge_crisp_dm(data.get('crisp_dm'), {'business_understanding': bu})
        # Prefer pipeline run state when provided
        run_id = data.get('pipeline_run_id')
        if run_id:
            try:
                run = PipelineRun.objects.get(pk=int(run_id))
                st = run.state or {}
                crisp = merge_crisp_dm(st.get('crisp_dm'), {'business_understanding': st.get('business_understanding') or bu})
                bu = crisp['business_understanding']
            except Exception:
                pass

        raw, filename = build_crisp_export_zip(
            settings.MEDIA_ROOT, file_id,
            business_understanding=bu, crisp_dm=crisp,
        )
        out_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, filename)
        with open(out_path, 'wb') as f:
            f.write(raw)
        resp = HttpResponse(raw, content_type='application/zip')
        resp['Content-Disposition'] = f'attachment; filename="{filename}"'
        resp['X-Export-Path'] = os.path.relpath(out_path, settings.MEDIA_ROOT)
        return resp


@method_decorator(csrf_exempt, name='dispatch')
class CrispMonitoringRunView(APIView):
    """Upload a scored/outcome batch CSV and compare to train reference."""

    def post(self, request, *args, **kwargs):
        file_id = request.POST.get('file_id') or (request.data or {}).get('file_id')
        if file_id is None:
            return Response({'error': 'file_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            file_id = int(file_id)
        except Exception:
            return Response({'error': 'file_id must be an integer'}, status=status.HTTP_400_BAD_REQUEST)

        upload = request.FILES.get('file')
        if upload is None:
            return Response({'error': 'file upload required'}, status=status.HTTP_400_BAD_REQUEST)

        score_col = request.POST.get('score_col') or request.data.get('score_col') or 'score'
        target_col = request.POST.get('target_col') or request.data.get('target_col')

        name = (upload.name or '').lower()
        raw = upload.read()
        try:
            if name.endswith(('.xlsx', '.xls')):
                current = pd.read_excel(io.BytesIO(raw))
            else:
                current = pd.read_csv(io.BytesIO(raw))
        except Exception as e:
            return Response({'error': f'Failed to parse upload: {e}'}, status=status.HTTP_400_BAD_REQUEST)

        # Reference: train_reference_head from bundle, else train_data head
        ref = None
        ref_path = os.path.join(
            settings.MEDIA_ROOT, 'deployment_bundles', str(file_id), 'train_reference_head.csv',
        )
        if os.path.exists(ref_path):
            ref = pd.read_csv(ref_path)
        else:
            pkl = os.path.join(settings.MEDIA_ROOT, 'train_data', f'{file_id}_train_data.pkl')
            if os.path.exists(pkl):
                with open(pkl, 'rb') as f:
                    td = pickle.load(f)
                Xtr = td.get('X_train')
                if Xtr is not None:
                    ref = Xtr.head(500).copy()

        if ref is None or ref.empty:
            return Response({
                'error': 'No train reference found. Create a deployment bundle or re-run modeling.',
            }, status=status.HTTP_404_NOT_FOUND)

        baseline = None
        eval_path = os.path.join(settings.MEDIA_ROOT, 'evaluation', f'{file_id}_evaluation.json')
        if os.path.exists(eval_path):
            try:
                with open(eval_path, 'r', encoding='utf-8') as f:
                    ev = json.load(f)
                baseline = (ev.get('evaluation') or ev).get('metrics')
            except Exception:
                pass

        report = compute_monitoring_report(
            ref, current,
            score_col=score_col if score_col in current.columns else None,
            target_col=target_col if target_col and target_col in current.columns else None,
            baseline_metrics=baseline,
        )
        mon_dir = os.path.join(settings.MEDIA_ROOT, 'monitoring')
        os.makedirs(mon_dir, exist_ok=True)
        mon_path = os.path.join(mon_dir, f'{file_id}_monitoring.json')
        with open(mon_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        return Response({
            'status': 'ok',
            'file_id': file_id,
            'monitoring': report,
            'path': os.path.relpath(mon_path, settings.MEDIA_ROOT),
        })


@method_decorator(csrf_exempt, name='dispatch')
class CrispSequentialPatternsView(APIView):
    """Sequential near-duplicate pattern flags on train data."""

    def get(self, request, file_id: int, *args, **kwargs):
        root = Path(settings.MEDIA_ROOT)
        execution_id = request.query_params.get('execution_id')
        try:
            if not execution_id:
                current = root / 'modeling' / f'{file_id}_status.json'
                execution_id = json.loads(current.read_text()).get('execution_id') if current.is_file() else None
            if not execution_id:
                if (root / 'train_data' / f'{file_id}_train_data.pkl').is_file():
                    return Response({'status': 'unavailable', 'error_code': 'sequential_provenance_unverified',
                        'error': 'Select a verified execution to inspect training-only sequential patterns.'},
                        status=status.HTTP_409_CONFLICT)
                return Response({'status': 'unavailable', 'error_code': 'sequential_training_missing',
                    'error': 'Training evidence is unavailable. Run modeling first.'}, status=status.HTTP_404_NOT_FOUND)
            payload, manifest = load_execution(execution_id, file_id)
            path = execution_artifact(execution_id, manifest, payload['model']['train_data_path'])
            if path == execution_root(execution_id).resolve() / 'final_holdout.pkl':
                raise ValueError('Protected outcome storage cannot be used for diagnostics.')
            with path.open('rb') as stream:
                development = pickle.load(stream)
            frame = development.get('X_train_raw')
            if frame is None:
                frame = development.get('X_train')
            if not isinstance(frame, pd.DataFrame):
                raise ValueError('The verified execution has no training predictor matrix.')
        except (OSError, ValueError, KeyError, TypeError, pickle.UnpicklingError, EOFError):
            return Response({'status': 'unavailable', 'error_code': 'sequential_execution_unverified',
                'error': 'Training predictors could not be verified for this execution.'},
                status=status.HTTP_409_CONFLICT)
        try:
            report = sequential_pattern_evidence(frame, time_col=request.query_params.get('time_col'))
        except (TypeError, ValueError):
            return Response({'status': 'unavailable', 'error_code': 'sequential_order_unavailable',
                'error': 'Choose an orderable column in the training predictors.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'status': 'ok',
            'scope': 'associational_near_duplicate_patterns',
            'limitation': DIAGNOSTIC_LIMITATIONS['sequential_patterns'],
            'evidence_partition': 'training_only',
            'execution_id': execution_id,
            'file_id': file_id,
            'n_candidates': len(report['candidates']),
            **report,
        })


@method_decorator(csrf_exempt, name='dispatch')
class CrispIterationCloneView(APIView):
    """Clone a pipeline run for iteration N+1 (preserve BU + dictionary pointers)."""

    def post(self, request, *args, **kwargs):
        data = request.data or {}
        run_id = data.get('pipeline_run_id')
        if run_id is None:
            return Response({'error': 'pipeline_run_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            parent = PipelineRun.objects.get(pk=int(run_id))
        except PipelineRun.DoesNotExist:
            return Response({'error': 'Pipeline run not found'}, status=status.HTTP_404_NOT_FOUND)

        parent_state = dict(parent.state or {})
        crisp = merge_crisp_dm(parent_state.get('crisp_dm'))
        crisp['iteration_id'] = int(crisp.get('iteration_id') or 1) + 1
        crisp['parent_run_id'] = parent.id
        crisp['phase_status']['modeling'] = 'pending'
        crisp['phase_status']['evaluation'] = 'pending'
        crisp['phase_status']['deployment'] = 'pending'
        crisp['phase_status']['monitoring'] = 'pending'
        crisp['champion'] = None
        crisp['monitoring'] = None

        # Reset modeling/eval artifacts in cloned state; keep BU + DQ + preprocessing
        new_state = {
            **parent_state,
            'crisp_dm': crisp,
            'business_understanding': crisp['business_understanding'],
            'modeling': None,
            'active_process': None,
            'flags': {
                **(parent_state.get('flags') or {}),
                'modeling_available': True,
                'is_started': True,
            },
        }
        from django.db import transaction
        with transaction.atomic():
            child = PipelineRun.objects.create(
                name=f"{parent.name} — iteration {crisp['iteration_id']}",
                pipeline_type=parent.pipeline_type,
                file_id=parent.file_id,
                current_step='modeling',
                status='active',
                state=new_state,
            )
            from access_control.projects import governed, bind_pipeline
            if governed():
                bind_pipeline(child, request._request._project_scopes[0]['project_id'], request.user)
        return Response({
            'status': 'ok',
            'parent_run_id': parent.id,
            'pipeline_run_id': child.id,
            'iteration_id': crisp['iteration_id'],
            'name': child.name,
            'state': new_state,
        }, status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name='dispatch')
class CrispDatqEnrichView(APIView):
    """Return DATQ rows with Shift_Recommendation keep/investigate/drop."""

    def get(self, request, file_id: int, *args, **kwargs):
        processed_file = request.query_params.get('processed_file')
        selected = managed_path(processed_file, table=True) if processed_file else None
        try:
            rows = read_datq(file_id, selected)
        except StageConflict as error:
            return Response({'error': str(error)}, status=status.HTTP_409_CONFLICT)
        if not rows:
            return Response({'error': 'DATQ summary not found'}, status=status.HTTP_404_NOT_FOUND)
        if isinstance(rows, dict):
            rows = rows.get('datq_summary') or rows.get('records') or []
        enriched = enrich_datq_with_recommendations(rows if isinstance(rows, list) else [])
        return Response({'status': 'ok', 'file_id': file_id, 'datq_summary': enriched})
