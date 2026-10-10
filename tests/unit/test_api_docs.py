"""docs/API.md is generated from the OpenAPI schema; it must never drift from the code."""

from scripts.export_api_docs import generate, main


def test_committed_api_reference_is_current():
    assert main(["--check"]) == 0, "run: python -m scripts.export_api_docs"


def test_reference_documents_every_route_and_the_auth_schemes():
    text = generate()
    for route in (
        "GET /incidents",
        "POST /webhook/incident",
        "POST /integrations/alertmanager",
        "POST /integrations/sentry",
        "POST /incidents/{incident_id}/remediation/decision",
    ):
        assert f"### `{route}`" in text
    assert "Authorization: Bearer" in text and "X-API-Key" in text
