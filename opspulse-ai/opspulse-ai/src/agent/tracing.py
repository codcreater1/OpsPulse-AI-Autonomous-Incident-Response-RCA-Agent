"""Langfuse tracing helpers (Developer 1)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.config import settings

logger = logging.getLogger(__name__)


def get_langfuse_handler() -> Optional[Any]:
    """Return a Langfuse LangChain CallbackHandler, or None when keys are not configured.

    Langfuse SDK v3/v4 reads LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST from the environment.
    """
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        logger.warning("Langfuse keys not set - tracing disabled")
        return None
    try:
        from langfuse.langchain import CallbackHandler  # SDK >= 3

        return CallbackHandler()
    except ImportError:
        try:
            from langfuse.callback import CallbackHandler  # type: ignore[no-redef]  # SDK 2.x

            return CallbackHandler()
        except Exception:  # pragma: no cover - defensive
            logger.exception("Langfuse handler import failed - tracing disabled")
            return None
    except Exception:  # pragma: no cover - defensive
        logger.exception("Langfuse handler init failed - tracing disabled")
        return None


def build_run_config(
    incident_id: str,
    repo_name: str,
    fingerprint: str,
    extra_tags: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """RunnableConfig for graph.invoke(): callbacks + Langfuse trace attributes."""
    config: Dict[str, Any] = {
        "run_name": "opspulse_incident_rca",
        "tags": ["opspulse", *(extra_tags or [])],
        "metadata": {
            "langfuse_session_id": incident_id,
            "langfuse_tags": ["opspulse", repo_name],
            "incident_id": incident_id,
            "repo_name": repo_name,
            "fingerprint": fingerprint,
        },
        "recursion_limit": 40,
    }
    handler = get_langfuse_handler()
    if handler is not None:
        config["callbacks"] = [handler]
    return config


def flush_langfuse() -> None:
    """Flush buffered spans (call at the end of a request / on shutdown)."""
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception:  # pragma: no cover - defensive
        logger.debug("Langfuse flush failed", exc_info=True)
