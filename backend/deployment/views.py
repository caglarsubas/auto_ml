"""Deployment API — freeze score bundle + batch score."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from django.http import HttpResponse
from deployment.scoring_receipts import byte_digest, csv_input, require_digest, scoring_runtime

from deployment.deploy_utils import (
    DeployNotReadyError,
    assess_file_deploy_readiness,
    build_deployment_pack_zip,
    build_score_bundle,
    bundle_summary,
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
            readiness = assess_file_deploy_readiness(int(file_id), request.query_params.get('execution_id'), request.query_params.get('assessment_id'))
            return Response({'file_id': int(file_id), 'readiness': readiness}, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_409_CONFLICT)
        except FileNotFoundError as e:
            return Response({'error': str(e)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request, *args, **kwargs):
        file_id = (request.data or {}).get('file_id')
        if file_id is None:
            return Response({'error': 'file_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            file_id = int(file_id)
            payload = build_score_bundle(file_id, request.data.get('execution_id'), request.data.get('assessment_id'))
            # Persist summary + advance pipeline when possible
            out_dir = os.path.join(settings.MEDIA_ROOT, 'deployment')
            os.makedirs(out_dir, exist_ok=True)
            summary_path = os.path.join(out_dir, f'{file_id}_bundle.json')
            # Compatibility summary is not authoritative; exact status reads verify the bundle.
            if payload['adoption_status'] == 'adopted':
                from modeling.execution_artifacts import projection_lock, replace_projection
                from deployment.evidence import read_json
                from deployment.deploy_utils import bundle_dir
                with projection_lock(file_id):
                    current = read_json(os.path.join(os.path.dirname(os.path.dirname(bundle_dir(file_id, payload['bundle_id']))), 'current.json'), {})
                    if current.get('bundle_id') == payload['bundle_id']:
                        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8') as staged:
                            json.dump(payload, staged, indent=2, default=str)
                            staged.flush()
                            replace_projection(staged.name, summary_path)
            payload['summary_path'] = os.path.relpath(summary_path, settings.MEDIA_ROOT)
            try:
                from modeling.models import PipelineRun
                run = PipelineRun.objects.filter(file_id=file_id).order_by('-updated_at').first()
                if run is not None and payload['adoption_status'] == 'adopted':
                    st = dict(run.state or {})
                    st['deployment'] = {
                        'bundle_path': payload.get('bundle_path'),
                        'bundle_id': payload['bundle_id'],
                        'execution_id': payload['execution_id'],
                        'assessment_id': payload['assessment_id'],
                        'manifest_sha256': payload['manifest_sha256'],
                        'lineage_id': (payload.get('manifest') or {}).get('lineage_id'),
                        'package_ready': True,
                        'production_use_approved': False,
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
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_409_CONFLICT)
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
                    input_receipt = csv_input(Path(tmp_path).read_bytes()) if tmp_path.endswith('.csv') else {
                        'format': 'excel', 'offline_verification_supported': False}
                finally:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
            elif isinstance(request.data.get('rows'), list):
                df = pd.DataFrame(request.data.get('rows'))
                input_receipt = {'format': 'json_rows', 'offline_verification_supported': False}
            else:
                return Response({
                    'error': 'Provide multipart file upload or JSON rows array.',
                }, status=status.HTTP_400_BAD_REQUEST)

            result = score_frame(file_id, df, bundle_id=request.data.get('bundle_id'))
            # Cap inline scores for large batches — also write artifact
            scores = result.get('scores') or []
            out_dir = os.path.join(settings.MEDIA_ROOT, 'deployment')
            os.makedirs(out_dir, exist_ok=True)
            batch_id = str(uuid.uuid4())
            batch_dir = os.path.join(out_dir, str(file_id), 'batches')
            os.makedirs(batch_dir, exist_ok=True)
            scored_path = os.path.join(batch_dir, f'{batch_id}.json')
            result['batch_id'] = batch_id
            result['receipt_schema_version'] = 1
            result['input'] = input_receipt
            result['scoring_runtime'] = scoring_runtime()
            result['offline_verification_scope'] = 'native_csv_batch_score_parity'
            with open(scored_path, 'x', encoding='utf-8') as f:
                json.dump(result, f, allow_nan=False)
            result['receipt_sha256'] = byte_digest(Path(scored_path).read_bytes())
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


class DeploymentReceiptView(APIView):
    """Read the exact full batch receipt under current dataset authority."""

    def get(self, request, file_id: int, batch_id: uuid.UUID, *args, **kwargs):
        try:
            expected = require_digest(request.query_params.get('sha256'))
            path = Path(settings.MEDIA_ROOT) / 'deployment' / str(file_id) / 'batches' / f'{batch_id}.json'
            if path.is_symlink():
                raise ValueError('Scoring receipt cannot be a symbolic link.')
            raw = path.read_bytes()
            if byte_digest(raw) != expected:
                raise ValueError('Scoring receipt changed; the requested digest does not match.')
            receipt = json.loads(raw)
            if receipt.get('file_id') != file_id or receipt.get('batch_id') != str(batch_id):
                raise ValueError('Scoring receipt identity does not match the requested batch.')
            response = HttpResponse(raw, content_type='application/json')
            response['Content-Disposition'] = f'attachment; filename="scoring-{batch_id}.json"'
            response['X-DeclarAI-Receipt-SHA256'] = expected
            response['Cache-Control'] = 'no-store'
            return response
        except FileNotFoundError:
            return Response({'error': 'Scoring receipt not found.'}, status=404)
        except (ValueError, TypeError, AttributeError):
            return Response({'error': 'Exact scoring receipt verification failed.'}, status=409)


@method_decorator(csrf_exempt, name='dispatch')
class DeploymentStatusView(APIView):
    def get(self, request, file_id: int, *args, **kwargs):
        try:
            return Response(bundle_summary(file_id, request.query_params.get('bundle_id')))
        except FileNotFoundError:
            return Response({'status': 'unknown', 'file_id': file_id})
        except ValueError as e:
            return Response({'status': 'error', 'error': str(e)}, status=status.HTTP_409_CONFLICT)


@method_decorator(csrf_exempt, name='dispatch')
class DeploymentPackView(APIView):
    """One-click deployment pack zip for review / regulatory handoff."""

    def post(self, request, *args, **kwargs):
        file_id = (request.data or {}).get('file_id')
        if file_id is None:
            return Response({'error': 'file_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            file_id = int(file_id)
            bundle_id = request.data.get('bundle_id')
            if bundle_id and (request.data.get('execution_id') or request.data.get('assessment_id')):
                raise ValueError('Select a bundle_id or an execution/assessment pair, not both.')
            if not bundle_id:
                payload = build_score_bundle(file_id, request.data.get('execution_id'), request.data.get('assessment_id'))
                bundle_id = payload['bundle_id']
            raw, filename = build_deployment_pack_zip(file_id, bundle_id)
            out_dir = os.path.join(settings.MEDIA_ROOT, 'exports')
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, filename), 'xb') as f:
                f.write(raw)
            resp = HttpResponse(raw, content_type='application/zip')
            resp['Content-Disposition'] = f'attachment; filename="{filename}"'
            summary = bundle_summary(file_id, bundle_id)
            resp['X-DeclarAI-Bundle-Id'] = summary['bundle_id']
            resp['X-DeclarAI-Manifest-SHA256'] = summary['manifest_sha256']
            return resp
        except DeployNotReadyError as e:
            return Response({'error': str(e), 'readiness': e.readiness}, status=status.HTTP_409_CONFLICT)
        except FileNotFoundError as e:
            return Response({'error': str(e)}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_409_CONFLICT)
        except Exception as e:
            import traceback
            print("[DeploymentPack] ERROR:\n" + traceback.format_exc())
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
