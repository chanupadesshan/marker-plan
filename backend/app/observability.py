"""
Optional Langfuse tracing for model calls. Does nothing unless the Langfuse keys are set.
"""

import logging
from functools import lru_cache
from .config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def _client():
    """
    Purpose: Create the shared Langfuse client once, or None when tracing is not configured.
    Input: none (keys and base URL come from the settings).
    Output: a Langfuse client, or None if the keys are missing or the client cannot start.
    """
    settings = get_settings()
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    try:
        from langfuse import Langfuse
        return Langfuse(public_key=settings.langfuse_public_key, secret_key=settings.langfuse_secret_key,
                        base_url=settings.langfuse_base_url or None)
    except Exception:
        logger.warning("Langfuse could not start; tracing is disabled", exc_info=True)
        return None


class ModelCallTrace:
    """
    Purpose: Record one model request attempt in Langfuse. Every method is safe to call when
    tracing is off, and a Langfuse failure never breaks an extraction.
    Input: model - the model name; name - the stage label; metadata - small non-sensitive fields;
    request_input - the prompt text, sent only when LANGFUSE_CAPTURE_CONTENT is true;
    document_id - groups every call for one upload into one trace and session; trace_name - its label.
    Output: a trace object; call finish(entry) once the attempt ends.
    """
    def __init__(self, model, name, metadata, request_input=None, document_id=None, trace_name=None):
        self._generation = None
        client = _client()
        if client is None:
            return
        try:
            from langfuse import propagate_attributes
            capture = get_settings().langfuse_capture_content
            # The same document_id always maps to the same trace, so every page and retry lands together.
            context = {"trace_id": client.create_trace_id(seed=str(document_id))} if document_id else None
            with propagate_attributes(session_id=str(document_id) if document_id else None, trace_name=trace_name):
                self._generation = client.start_observation(
                    as_type="generation", name=name, model=model, metadata=metadata, trace_context=context,
                    input=request_input if capture else None)
        except Exception:
            logger.warning("Langfuse trace failed", exc_info=True)

    def finish(self, entry, output=None):
        """
        Purpose: Close the trace with the attempt's token usage and status.
        Input: entry - the attempt's usage record from request_usage; output - the reply text,
        sent only when LANGFUSE_CAPTURE_CONTENT is true.
        Output: nothing.
        """
        if self._generation is None:
            return
        try:
            usage = {key: entry[src] for key, src in (("input", "input_tokens"), ("output", "output_tokens"),
                                                      ("total", "total_tokens")) if entry.get(src) is not None}
            ok = entry.get("status") == "success"
            self._generation.update(
                usage_details=usage or None,
                cost_details={"total": entry["cost_usd"]} if entry.get("cost_usd") is not None else None,
                output=output if get_settings().langfuse_capture_content else None,
                level="DEFAULT" if ok else "ERROR",
                status_message=entry.get("status"),
                metadata={"request_id": entry.get("request_id"), "finish_reason": entry.get("finish_reason"),
                          "attempt": entry.get("attempt"), "status": entry.get("status")})
            self._generation.end()
        except Exception:
            logger.warning("Langfuse trace failed", exc_info=True)


def flush():
    """
    Purpose: Send any queued traces; call when the app shuts down.
    Input: none.
    Output: nothing.
    """
    client = _client()
    if client is not None:
        client.flush()
