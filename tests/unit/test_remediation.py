import uuid

import pytest

from src.services.remediation_service import (
    PatchRejectedError,
    ProposedFix,
    build_pull_request_body,
    build_pull_request_title,
    validate_patch_for_pr,
)
from tests.unit.factories import GOOD_DIFF, make_analysis


def test_valid_patch_passes_policy():
    validate_patch_for_pr(GOOD_DIFF, "src/app.py", 40)


@pytest.mark.parametrize(
    "patch,target,limit,reason",
    [
        (None, "src/app.py", 40, "no patch"),
        ("not a diff", "src/app.py", 40, "malformed"),
        (GOOD_DIFF, "src/other.py", 40, "does not match"),
        (GOOD_DIFF + GOOD_DIFF.replace("src/app.py", "src/b.py"), "src/app.py", 40, "exactly one file"),
        (GOOD_DIFF.replace("src/app.py", ".github/workflows/ci.yml"), ".github/workflows/ci.yml", 40, "protected"),
        (GOOD_DIFF, "src/app.py", 1, "limit 1"),
    ],
)
def test_policy_rejections(patch, target, limit, reason):
    with pytest.raises(PatchRejectedError, match=reason):
        validate_patch_for_pr(patch, target, limit)


def _fix():
    analysis = make_analysis()
    analysis["incident_summary"]["title"] = "Crash\nping @security-team now"
    analysis["evaluation"] = {"checks": {"schema": {"score": 0.1, "max": 0.1}}}
    return ProposedFix(uuid.uuid4(), "o/r", "f" * 64, "src/app.py", GOOD_DIFF, analysis, 0.9, 2)


def test_pr_text_is_honest_and_neutralizes_mentions():
    fix = _fix()
    body = build_pull_request_body(fix, reviewer="alice")
    title = build_pull_request_title(fix.analysis)
    assert "No tests were executed by OpsPulse AI" in body and "not a probability" in body
    assert "- [ ] call load_user({}) and expect ValueError" in body
    assert "@security-team" not in title and "\n" not in title
