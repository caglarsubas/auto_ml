from django.db import DatabaseError
from rest_framework.response import Response
from rest_framework.views import APIView
from access_control.assistant_approvals import ApprovalError, prepare, approve, cancel, status


class AssistantApprovalView(APIView):
    operation = staticmethod(prepare)

    def post(self, request):
        try:
            if not isinstance(request.data, dict):
                raise ApprovalError("invalid_action_payload", "Supply a JSON action object.", 400)
            return Response(self.operation(request.user, request.data))
        except (DatabaseError, OSError):
            return Response(
                {
                    "status": "error",
                    "error_code": "action_receipt_unavailable",
                    "error": "Action authority cannot be recorded. Restore the service before continuing.",
                },
                status=503,
            )
        except ApprovalError as exc:
            return Response({"status": "error", "error_code": exc.code, "error": exc.message}, status=exc.status)


class AssistantApproveView(AssistantApprovalView):
    operation = staticmethod(approve)


class AssistantCancelView(AssistantApprovalView):
    operation = staticmethod(cancel)


class AssistantReceiptView(APIView):
    def get(self, request, approval_id):
        try:
            return Response(
                status(
                    request.user,
                    {"approval_id": str(approval_id), "proposal_sha256": request.query_params.get("proposal_sha256")},
                )
            )
        except (DatabaseError, OSError):
            return Response(
                {
                    "status": "error",
                    "error_code": "action_receipt_unavailable",
                    "error": "Action authority cannot be recorded. Restore the service before continuing.",
                },
                status=503,
            )
        except ApprovalError as exc:
            return Response({"status": "error", "error_code": exc.code, "error": exc.message}, status=exc.status)
