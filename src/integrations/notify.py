"""Reviewer notifications via an incoming-webhook URL (Slack- and Mattermost-compatible `{"text": ...}`).

Sent when an incident reaches a status listed in NOTIFY_ON_STATUSES (default: awaiting_approval, failed).
The message carries only status, repository, a short title, the quality score and a console link - never stack
traces, source code, patches or error text from the application. Delivery failures are logged and counted;
they never affect incident processing.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from src import metrics
from src.config import settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5


def _clean(text: Any, limit: int) -> str:
    """Model-written text: one line, bounded, no @-mentions or link markup that could ping or mislead."""
    value = " ".join(str(text or "").split())
    for char in ("@", "<", ">"):
        value = value.replace(char, " ")
    return value if len(value) <= limit else value[: limit - 1] + "…"


def build_message(incident: dict[str, Any]) -> dict[str, str]:
    analysis = incident.get("analysis") or {}
    title = _clean((analysis.get("incident_summary") or {}).get("title") or "Incident", 120)
    status = str(incident.get("status", "")).replace("_", " ")
    lines = [
        f"OpsPulse: {status} - {incident.get('repo_name')}",
        f"{title}",
        f"Quality score {float(incident.get('quality_score') or 0):.2f}"
        + (f" | category {incident['error_category']}" if incident.get("error_category") else ""),
    ]
    if settings.public_base_url:
        lines.append(f"Review: {settings.public_base_url.rstrip('/')}/console (incident {incident['incident_id']})")
    else:
        lines.append(f"Incident {incident['incident_id']}")
    return {"text": "\n".join(lines)}


def notify_incident(incident: dict[str, Any]) -> bool:
    """Send a notification if configured and the status is selected. Returns True if one was delivered."""
    if not settings.notify_webhook_url or incident.get("status") not in settings.notify_on_statuses:
        return False
    try:
        response = requests.post(settings.notify_webhook_url, json=build_message(incident), timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("notification failed: %s", type(exc).__name__)
        metrics.NOTIFICATIONS.labels("failed").inc()
        return False
    metrics.NOTIFICATIONS.labels("sent").inc()
    return True
