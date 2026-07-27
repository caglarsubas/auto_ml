"""Deployment API — freeze score bundle + batch score."""

from __future__ import annotations

import json
import os
import tempfile

import pandas as pd
from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from django.http import HttpResponse

from deployment.deploy_utils import (
    DeployNotReadyError,
    assess_file_deploy_readiness,
    build_deployment_pack_zip,
    build_score_bundle,
    score_frame,
)


@method_decorator(csrf_exempt, name='dispatch')
class DeploymentBundleView(APIView):
    """Create a frozen score bundle for a modeled file_id.

    Payload: { file_id: int }
    """

    def get(self, request, *args, **kwargs):
        """Return deploy-readiness assessment without creating a bundle."""
        file_id = request.query_params.get('file_id') or (request.data or {}).get('file_id')
        if file_id is None:
            return Response({'error': 'file_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            readiness = assess_file_deploy_readiness(int(file_id))
            return Response({'file_id': int(file_id), 'readiness': readiness}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request, *args, **kwargs):
        file_id = (request.data or {}).get('file_id')
        if file_id is None:
            return Response({'error': 'file_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            file_id = int(file_id)
            payload = build_score_bundle(file_id)
            # Persist summary + advance pipeline when possible
            out_dir = os.path.join(settings.MEDIA_ROOT, 'deployment')
            os.makedirs(out_dir, exist_ok=True)
            summary_path = os.path.join(out_dir, f'{file_id}_bundle.json')
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2, default=str)
            payload['summary_path'] = os.path.relpath(summary_path, settings.MEDIA_ROOT)
            try:
                from modeling.models import PipelineRun
                run = PipelineRun.objects.filter(file_id=file_id).order_by('-updated_at').first()
                if run is not None:
                    st = dict(run.state or {})
                    st['deployment'] = {
                        'bundle_path': payload.get('bundle_path'),
                        'lineage_id': (payload.get('manifest') or {}).get('lineage_id'),
                        'deploy_ready': True,
                    }
                    step_order = {
                        'declaration': 0, 'preprocessing': 1, 'data_quality': 2,
                        'modeling': 3, 'sfs': 4, 'evaluation': 5, 'deployment': 6,
                    }
                    cur = run.current_step or 'evaluation'
                    if step_order.get('deployment', 6) >= step_order.get(cur, 0):
                        run.current_step = 'deployment'
                    run.state = st
                    run.save(update_fields=['current_step', 'state', 'updated_at'])
            except Exception as pe:
                print(f"[Deployment] PipelineRun update skipped: {pe}")
            return Response(payload, status=status.HTTP_200_OK)
        except DeployNotReadyError as e:
            return Response({
                'error': str(e),
                'deploy_ready': False,
                'readiness': e.readiness,
                'blocking': (e.readiness or {}).get('blocking') or [],
            }, status=status.HTTP_409_CONFLICT)
        except FileNotFoundError as e:
            return Response({'error': str(e)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            import traceback
            print("[DeploymentBundle] ERROR:\n" + traceback.format_exc())
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class DeploymentScoreView(APIView):
    """Batch-score a CSV using the frozen bundle.

    Accepts multipart file upload ``file`` or JSON ``{ file_id, rows: [...] }``.
    """

    def post(self, request, *args, **kwargs):
        file_id = request.data.get('file_id')
        if file_id is None:
            return Response({'error': 'file_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            file_id = int(file_id)
        except Exception:
            return Response({'error': 'file_id must be an integer'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if request.FILES.get('file'):
                uploaded = request.FILES['file']
                name = getattr(uploaded, 'name', 'upload.csv').lower()
                with tempfile.NamedTemporaryFile(suffix=os.path.splitext(name)[1] or '.csv', delete=False) as tmp:
                    for chunk in uploaded.chunks():
                        tmp.write(chunk)
                    tmp_path = tmp.name
                try:
                    df = pd.read_csv(tmp_path) if tmp_path.endswith('.csv') else pd.read_excel(tmp_path)
                finally:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
            elif isinstance(request.data.get('rows'), list):
                df = pd.DataFrame(request.data.get('rows'))
            else:
                return Response({
                    'error': 'Provide multipart file upload or JSON rows array.',
                }, status=status.HTTP_400_BAD_REQUEST)

            result = score_frame(file_id, df)
            # Cap inline scores for large batches — also write artifact
            scores = result.get('scores') or []
            out_dir = os.path.join(settings.MEDIA_ROOT, 'deployment')
            os.makedirs(out_dir, exist_ok=True)
            scored_path = os.path.join(out_dir, f'{file_id}_scores.json')
            with open(scored_path, 'w', encoding='utf-8') as f:
                json.dump(result, f)
            result['scores_path'] = os.path.relpath(scored_path, settings.MEDIA_ROOT)
            if len(scores) > 500:
                result['scores_preview'] = scores[:500]
                result['scores_truncated'] = True
                result.pop('scores', None)
            return Response(result, status=status.HTTP_200_OK)
        except FileNotFoundError as e:
            return Response({'error': str(e)}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            import traceback
            print("[DeploymentScore] ERROR:\n" + traceback.format_exc())
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class DeploymentStatusView(APIView):
    def get(self, request, file_id: int, *args, **kwargs):
        path = os.path.join(settings.MEDIA_ROOT, 'deployment', f'{file_id}_bundle.json')
        if not os.path.exists(path):
            return Response({'status': 'unknown', 'file_id': file_id}, status=status.HTTP_200_OK)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            payload['status'] = 'ok'
            return Response(payload, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'status': 'error', 'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@method_decorator(csrf_exempt, name='dispatch')
class DeploymentPackView(APIView):
    """One-click deployment pack zip for review / regulatory handoff."""

    def post(self, request, *args, **kwargs):
        file_id = (request.data or {}).get('file_id')
        if file_id is None:
            return Response({'error': 'file_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            file_id = int(file_id)
            # Ensure bundle exists (create if deploy-ready)
            try:
                build_score_bundle(file_id)
            except DeployNotReadyError as e:
                return Response({
                    'error': str(e),
                    'deploy_ready': False,
                    'readiness': e.readiness,
                }, status=status.HTTP_409_CONFLICT)
            except FileNotFoundError as e:
                return Response({'error': str(e)}, status=status.HTTP_404_NOT_FOUND)

            raw, filename = build_deployment_pack_zip(file_id)
            out_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, filename), 'wb') as f:
                f.write(raw)
            resp = HttpResponse(raw, content_type='application/zip')
            resp['Content-Disposition'] = f'attachment; filename="{filename}"'
            return resp
        except Exception as e:
            import traceback
            print("[DeploymentPack] ERROR:\n" + traceback.format_exc())
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
