"""Deterministic test data shared by the unit tests."""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from typing import Any

from src.agent.patching import format_code_window
from src.integrations.github import SourceContext

REPO = "o/r"

SOURCE = """import json


def load_user(data):
    profile = data.get("profile")
    name = profile["name"]
    email = profile["email"]
    return {"name": name, "email": email}


def main():
    print(load_user({}))
"""

TRACE = """Traceback (most recent call last):
  File "/app/src/app.py", line 14, in main
    print(load_user({}))
  File "/app/src/app.py", line 6, in load_user
    name = profile["name"]
TypeError: 'NoneType' object is not subscriptable
"""

ERROR = "TypeError: 'NoneType' object is not subscriptable"

GOOD_DIFF = """--- a/src/app.py
+++ b/src/app.py
@@ -3,6 +3,8 @@

 def load_user(data):
     profile = data.get("profile")
+    if profile is None:
+        raise ValueError("missing profile")
     name = profile["name"]
     email = profile["email"]
     return {"name": name, "email": email}
"""

BAD_DIFF = GOOD_DIFF.replace('    profile = data.get("profile")', '    profile = data.get("profil")')

SOURCE_CONTEXT = SourceContext("src/app.py", "abc123456789", 1, 13, 6, format_code_window(SOURCE.splitlines(), 1), [])


def make_analysis(
    diff: str = GOOD_DIFF,
    confidence: float = 0.8,
    trigger: str = "src/app.py:6 -> load_user()",
    quote: str = 'name = profile["name"]',
    quote_source: str = "code_context",
    evidence_sufficient: bool = True,
) -> dict[str, Any]:
    return {
        "incident_summary": {
            "title": "Missing profile crashes load_user",
            "severity": "HIGH",
            "failing_service": "demo",
            "trigger_frame": trigger,
        },
        "root_cause_category": "null_reference",
        "hypotheses": [
            {"id": "H1", "description": "profile key absent", "evidence": "data.get returns None", "likelihood": 0.8},
            {"id": "H2", "description": "wrong input type", "evidence": "input is a dict", "likelihood": 0.1},
        ],
        "evidence": [
            {"kind": "observed", "claim": "failing line subscripts profile", "source": quote_source, "quote": quote},
            {
                "kind": "observed",
                "claim": "the error is a None subscript",
                "source": "stack_trace",
                "quote": "'NoneType' object is not subscriptable",
            },
            {"kind": "inference", "claim": "callers may omit 'profile'", "source": "none", "quote": ""},
        ],
        "affected_files": ["src/app.py"],
        "diagnostic_chain": {
            "primary_root_cause": {
                "hypothesis_id": "H1",
                "technical_explanation": "dict.get returns None when the key is missing",
                "symptom_vs_cause": "TypeError is the symptom; the missing key is the cause",
                "justification": "stack trace shows a subscript on None",
            }
        },
        "patch_remediation": {
            "explanation": "guard against None",
            "side_effects": "raises ValueError instead",
            "unified_diff": diff,
        },
        "uncertainties": ["whether callers rely on the TypeError"],
        "tests_to_run": ["call load_user({}) and expect ValueError"],
        "control_flow": {
            "self_assessed_confidence": confidence,
            "needs_human_review": False,
            "evidence_sufficient": evidence_sufficient,
        },
    }


class FakeLLM:
    """Returns queued replies (dicts are JSON-encoded, strings returned verbatim); records prompts."""

    def __init__(self, replies: list[Any]) -> None:
        self.replies = [copy.deepcopy(r) for r in replies]
        self.prompts: list[str] = []

    def invoke(self, messages: list[Any], config: Any = None) -> SimpleNamespace:
        self.prompts.append(messages[-1].content)
        reply = self.replies.pop(0)
        return SimpleNamespace(content=reply if isinstance(reply, str) else json.dumps(reply))

    @property
    def calls(self) -> int:
        return len(self.prompts)


def incident_payload(**overrides: Any) -> dict[str, Any]:
    return {"repo_name": REPO, "error_message": ERROR, "stack_trace": TRACE, **overrides}
