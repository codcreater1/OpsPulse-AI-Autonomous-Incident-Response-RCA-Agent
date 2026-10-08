import os
import tempfile

_DB = os.path.join(tempfile.mkdtemp(prefix="opspulse-test-"), "test.db")
os.environ["NEON_DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["LANGFUSE_PUBLIC_KEY"] = ""
os.environ["LANGFUSE_SECRET_KEY"] = ""
os.environ["WEBHOOK_SECRET"] = ""

import pytest  # noqa: E402

from src.db.client import get_engine, init_db  # noqa: E402
from src.db.models import Base  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(get_engine())
    init_db()
    yield


SOURCE = """import json


def load_user(data):
    profile = data.get("profile")
    name = profile["name"]
    email = profile["email"]
    return {"name": name, "email": email}


def main():
    print(load_user({}))
"""

TRACE = '''Traceback (most recent call last):
  File "/app/src/app.py", line 14, in main
    print(load_user({}))
  File "/app/src/app.py", line 6, in load_user
    name = profile["name"]
TypeError: 'NoneType' object is not subscriptable
'''

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


def make_analysis(diff: str, confidence: float = 0.9, trigger: str = "src/app.py:6 -> load_user()") -> dict:
    return {
        "incident_summary": {"title": "Missing profile crashes load_user", "severity": "HIGH",
                             "failing_service": "demo", "trigger_frame": trigger},
        "hypotheses": [
            {"id": "H1", "description": "profile key absent", "evidence": "data.get returns None", "likelihood": 0.8},
            {"id": "H2", "description": "wrong input type", "evidence": "input is a dict", "likelihood": 0.1},
        ],
        "diagnostic_chain": {"primary_root_cause": {
            "hypothesis_id": "H1", "technical_explanation": "dict.get returns None when key missing",
            "symptom_vs_cause": "TypeError is the symptom; the missing key is the cause",
            "justification": "stack trace shows subscript on None"}},
        "patch_remediation": {"explanation": "guard against None", "side_effects": "none", "unified_diff": diff},
        "control_flow": {"self_assessed_confidence": confidence, "needs_human_review": False},
    }
