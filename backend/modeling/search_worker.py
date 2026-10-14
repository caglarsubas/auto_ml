"""Start process-local workers without leaving a false running owner on failure."""
import threading

from modeling.async_failures import record_failure
from modeling.search_admission import fail_search_launch


def launch_search_worker(registry, file_id, target, context, *, thread_factory=None):
    owner, thread = registry.get(file_id), None
    try:
        if owner is None or owner.get("operation_id") != context["operation_id"] or owner.get("status") != "running":
            raise ValueError("Search launch requires its current running owner.")
        thread = (thread_factory or threading.Thread)(target=target)
        thread.daemon = True
        thread.start()
    except Exception as error:
        failure = record_failure(error, "worker_start", context)
        try:
            may_have_started = thread is not None and getattr(thread, "ident", None) is not None
        except Exception:
            # Failed introspection cannot justify releasing a possibly active owner.
            may_have_started = True
        message = "The background worker could not start. Retry when resources are available."
        failed = fail_search_launch(registry, file_id, owner, context["operation_id"],
                                    failure, may_have_started, message)
        return {
            "status": "error" if failed else "unavailable",
            "error_code": "search_worker_start_failed" if failed else "search_worker_start_uncertain",
            "error": message if failed else "Worker launch is uncertain. Inspect this operation's status before retrying.",
            "file_id": file_id, "operation_id": context["operation_id"], "failure": failure,
        }
    return None
