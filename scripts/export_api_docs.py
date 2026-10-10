"""Write docs/API.md from the application's own OpenAPI schema, so the reference cannot drift from the code.

python -m scripts.export_api_docs           # regenerate docs/API.md
python -m scripts.export_api_docs --check   # exit 1 if the committed file is out of date (used by a unit test)
"""

from __future__ import annotations

import argparse
import os
import pathlib
import sys
from typing import Any

os.environ.setdefault("DATABASE_URL", "sqlite://")

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "API.md"
TAG_ORDER = ["incidents", "remediation", "integrations", "health"]
TAG_TITLES = {
    "incidents": "Incidents",
    "remediation": "Remediation decisions",
    "integrations": "Inbound integrations",
    "health": "Health and metrics",
}


def _ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def _type(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return _ref_name(schema["$ref"])
    if "anyOf" in schema:
        return " or ".join(_type(s) for s in schema["anyOf"])
    kind = schema.get("type", "any")
    if kind == "array":
        return f"list of {_type(schema.get('items', {}))}"
    if "enum" in schema:
        return "one of " + ", ".join(f"`{v}`" for v in schema["enum"])
    return str(kind)


def _fields(spec: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    if "$ref" in schema:
        schema = spec["components"]["schemas"][_ref_name(schema["$ref"])]
    required = set(schema.get("required", []))
    rows = []
    for name, field in schema.get("properties", {}).items():
        note = (field.get("description") or "").replace("\n", " ")
        rows.append(f"| `{name}` | {_type(field)} | {'yes' if name in required else ''} | {note} |")
    return rows


def render(spec: dict[str, Any]) -> str:
    lines = [
        "# API reference",
        "",
        "Generated from the application's OpenAPI schema by `python -m scripts.export_api_docs` "
        "(a unit test fails when this file is out of date). The live, interactive version is served at `/docs`.",
        "",
        "**Authentication.** Send an API key as `X-API-Key: <key>` or `Authorization: Bearer <key>`. Roles: "
        "`reporter` (submit and read), `reviewer` (also decide remediation), `admin`. The Sentry webhook is "
        "authenticated by its HMAC signature instead.",
        "",
    ]
    by_tag: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    for path, operations in spec["paths"].items():
        for method, op in operations.items():
            by_tag.setdefault((op.get("tags") or ["other"])[0], []).append((method.upper(), path, op))
    for tag in sorted(by_tag, key=lambda t: TAG_ORDER.index(t) if t in TAG_ORDER else 99):
        lines += [f"## {TAG_TITLES.get(tag, tag.title())}", ""]
        for method, path, op in by_tag[tag]:
            lines += [f"### `{method} {path}`", ""]
            description = (op.get("description") or op.get("summary") or "").strip()
            if description:
                lines += [description, ""]
            auth = "API key or Bearer token" if op.get("security") else "none (see description)"
            lines += [f"**Auth:** {auth}", ""]
            params = [p for p in op.get("parameters", []) if p.get("in") in ("query", "path")]
            if params:
                lines += ["| Parameter | In | Type | Required | Description |", "|---|---|---|---|---|"]
                for p in params:
                    note = (p.get("description") or "").replace("\n", " ")
                    lines.append(
                        f"| `{p['name']}` | {p['in']} | {_type(p.get('schema', {}))} | "
                        f"{'yes' if p.get('required') else ''} | {note} |"
                    )
                lines.append("")
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema")
            if body:
                rows = _fields(spec, body)
                if rows:
                    lines += [
                        "**JSON body**",
                        "",
                        "| Field | Type | Required | Description |",
                        "|---|---|---|---|",
                        *rows,
                        "",
                    ]
            lines += ["| Status | Meaning |", "|---|---|"]
            for code, response in op.get("responses", {}).items():
                meaning = (response.get("description") or "").replace("\n", " ")
                lines.append(f"| {code} | {meaning} |")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def generate() -> str:
    from src.main import app

    return render(app.openapi())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    text = generate()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current.replace("\r\n", "\n") != text:
            print("docs/API.md is out of date: run python -m scripts.export_api_docs", file=sys.stderr)
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
