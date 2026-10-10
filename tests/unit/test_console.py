"""The review console is served with a strict CSP and renders untrusted data only via textContent."""

import pathlib
import re

from src.console import STATIC_DIR


def test_console_page_has_strict_csp_and_security_headers(client):
    resp = client.get("/console")
    assert resp.status_code == 200 and "text/html" in resp.headers["content-type"]
    csp = resp.headers["content-security-policy"]
    assert "script-src 'self'" in csp and "frame-ancestors 'none'" in csp and "unsafe-inline" not in csp
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["cache-control"] == "no-store"


def test_static_assets_are_served(client):
    for name, kind in (("app.js", "javascript"), ("styles.css", "css")):
        resp = client.get(f"/console/static/{name}")
        assert resp.status_code == 200 and kind in resp.headers["content-type"]


def test_api_responses_carry_baseline_security_headers(client):
    resp = client.get("/healthz")
    assert resp.headers["x-frame-options"] == "DENY" and resp.headers["referrer-policy"] == "no-referrer"


def test_console_has_no_inline_script_or_unsafe_dom_sinks():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), "inline <script> would violate the CSP"
    assert not re.search(r"\sstyle\s*=", html), "inline styles would violate the CSP"
    assert not re.search(r"\son[a-z]+\s*=", html), "inline event handlers would violate the CSP"
    source = pathlib.Path(STATIC_DIR / "app.js").read_text(encoding="utf-8")
    js = "\n".join(line for line in source.splitlines() if not line.strip().startswith("//"))  # ignore comments
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert sink not in js, f"{sink} must not be used with untrusted data"


def test_console_can_be_disabled(monkeypatch):
    import importlib

    import src.main as main_module

    monkeypatch.setenv("CONSOLE_ENABLED", "false")
    try:
        from src import config

        monkeypatch.setattr(config, "settings", config.Settings())
        reloaded = importlib.reload(main_module)
        paths = {getattr(route, "path", None) for route in reloaded.app.routes}
        assert "/console" not in paths
    finally:
        monkeypatch.undo()
        importlib.reload(main_module)


def test_console_loads_nothing_from_other_origins_and_never_sets_a_style_attribute():
    sources = {name: (STATIC_DIR / name).read_text(encoding="utf-8") for name in ("index.html", "app.js", "styles.css")}
    for name, text in sources.items():
        assert not re.search(r"https?://(?!localhost)", re.sub(r"//.*", "", text)), f"{name} references another origin"
        assert "@import" not in text and "url(" not in sources["styles.css"]
    js = sources["app.js"]
    assert 'setAttribute("style"' not in js and "cssText" not in js  # CSSOM property writes only (CSP-safe)
    assert 'href="/console/static/styles.css"' in sources["index.html"]


def test_console_has_the_confirmation_dialog_and_live_regions():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert "<dialog" in html and 'aria-live="polite"' in html and 'class="skip-link"' in html
    assert 'id="approve"' in html and 'id="confirm-ok"' in html


def test_console_script_is_syntactically_valid():
    import shutil
    import subprocess

    import pytest

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    args = [node, "--check", str(STATIC_DIR / "app.js")]  # fixed arguments, no untrusted input
    result = subprocess.run(args, capture_output=True, text=True, check=False)  # noqa: S603
    assert result.returncode == 0, result.stderr
