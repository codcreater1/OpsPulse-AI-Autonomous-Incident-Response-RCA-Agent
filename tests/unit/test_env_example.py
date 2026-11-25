"""`.env.example` is the operator's list of settings: one the application reads but the file omits is invisible."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Names `src/config.py` accepts for compatibility. The first, documented name is in `.env.example`; these are aliases.
LEGACY_ALIASES = {"GROQ_MODEL", "NEON_DATABASE_URL", "CONFIDENCE_THRESHOLD", "MAX_ITERATIONS"}
NOT_SETTINGS = {"INFO"}  # a default value (the log level), matched by the pattern below


def _read_by_the_application() -> set[str]:
    return set(re.findall(r'"([A-Z][A-Z0-9_]{2,})"', (ROOT / "src" / "config.py").read_text(encoding="utf-8")))


def _listed_in_the_example() -> set[str]:
    return set(
        re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", (ROOT / ".env.example").read_text(encoding="utf-8"), re.MULTILINE)
    )


def test_every_setting_the_application_reads_is_listed_in_env_example():
    missing = _read_by_the_application() - _listed_in_the_example() - LEGACY_ALIASES - NOT_SETTINGS
    assert not missing, f"add these to .env.example (with a comment saying what they do): {sorted(missing)}"


def test_env_example_lists_nothing_the_application_ignores():
    stale = _listed_in_the_example() - _read_by_the_application()
    assert not stale, f"these are in .env.example but src/config.py never reads them: {sorted(stale)}"


def test_env_example_has_placeholders_only():
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    for name in ("GROQ_API_KEY", "GITHUB_TOKEN", "LANGFUSE_SECRET_KEY", "API_KEY"):
        assert re.search(rf"^{name}=\s*$", text, re.MULTILINE) or f"{name}=" not in text, (
            f"{name} must be empty in the example"
        )
