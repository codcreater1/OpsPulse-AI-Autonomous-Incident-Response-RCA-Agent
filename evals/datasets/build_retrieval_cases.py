"""Authoring script for retrieval_cases.json (run: python -m evals.datasets.build_retrieval_cases).

Relevance labels are assigned by construction: every historical incident belongs to a root-cause `group`
written by the author; a historical incident is relevant to a query iff it is in the same repository AND the
same group. Some groups deliberately share no wording (e.g. different attribute names on a None object), so
lexical retrieval is expected to miss them - that is a measured limitation, not a bug in the labels.
"""

from __future__ import annotations

import json
import pathlib

OUT = pathlib.Path(__file__).with_name("retrieval_cases.json")


def trace(path: str, func: str, stmt: str, final: str, line: int = 10) -> str:
    return f'Traceback (most recent call last):\n  File "/app/{path}", line {line}, in {func}\n    {stmt}\n{final}'


# Newest first (the order the database query returns candidates in).
CORPUS = [
    (
        "h01",
        "shop",
        "currency",
        "billing/invoice.py",
        "KeyError: 'currency'",
        trace("billing/invoice.py", "invoice_currency", 'return order["currency"].upper()', "KeyError: 'currency'"),
    ),
    (
        "h02",
        "shop",
        "currency",
        "billing/invoice.py",
        "KeyError: 'currency'",  # repeated delivery of h01's failure
        trace("billing/invoice.py", "invoice_currency", 'return order["currency"].upper()', "KeyError: 'currency'", 11),
    ),
    (
        "h03",
        "shop",
        "currency",
        "billing/totals.py",
        "KeyError: 'currency'",
        trace("billing/totals.py", "total_with_tax", 'rate = TAX[order["currency"]]', "KeyError: 'currency'"),
    ),
    (
        "h04",
        "shop",
        "db-down",
        "app/db/pool.py",
        "psycopg2.OperationalError: could not connect to server: Connection refused",
        trace(
            "app/db/pool.py",
            "connect",
            "conn = psycopg2.connect(dsn)",
            "psycopg2.OperationalError: could not connect to server: Connection refused",
        ),
    ),
    (
        "h05",
        "shop",
        "db-down",
        "workers/sync.py",
        "psycopg2.OperationalError: could not connect to server: Connection refused",
        trace(
            "workers/sync.py",
            "run_sync",
            "with get_connection() as conn:",
            "psycopg2.OperationalError: could not connect to server: Connection refused",
        ),
    ),
    (
        "h06",
        "shop",
        "none-user",
        "app/notify.py",
        "AttributeError: 'NoneType' object has no attribute 'email'",
        trace(
            "app/notify.py",
            "notify",
            "send_mail(user.email)",
            "AttributeError: 'NoneType' object has no attribute 'email'",
        ),
    ),
    (
        "h07",
        "shop",
        "bad-upstream-json",
        "app/rates.py",
        "json.decoder.JSONDecodeError: Expecting value: line 1 column 1",
        trace(
            "app/rates.py",
            "fetch_rates",
            "return response.json()",
            "json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)",
        ),
    ),
    (
        "h08",
        "shop",
        "payment-timeout",
        "app/payments.py",
        "requests.exceptions.ReadTimeout: HTTPSConnectionPool(host='pay.example.test', port=443): Read timed out.",
        trace(
            "app/payments.py",
            "charge",
            "resp = session.post(url, json=body, timeout=10)",
            "requests.exceptions.ReadTimeout: HTTPSConnectionPool(host='pay.example.test', port=443): Read timed out.",
        ),
    ),
    (
        "h09",
        "shop",
        "noise-div",
        "app/stats.py",
        "ZeroDivisionError: division by zero",
        trace("app/stats.py", "average", "return sum(values) / len(values)", "ZeroDivisionError: division by zero"),
    ),
    (
        "h10",
        "shop",
        "noise-import",
        "app/settings.py",
        "ModuleNotFoundError: No module named 'yaml'",
        trace("app/settings.py", "<module>", "import yaml", "ModuleNotFoundError: No module named 'yaml'"),
    ),
    (
        "h11",
        "shop",
        "noise-recursion",
        "app/tree.py",
        "RecursionError: maximum recursion depth exceeded",
        trace(
            "app/tree.py",
            "depth",
            "return 1 + max(depth(c) for c in node['children'])",
            "RecursionError: maximum recursion depth exceeded",
        ),
    ),
    # Another tenant's repository with the same failures: must never be returned for "shop" queries.
    (
        "o01",
        "other",
        "currency",
        "billing/invoice.py",
        "KeyError: 'currency'",
        trace("billing/invoice.py", "invoice_currency", 'return order["currency"].upper()', "KeyError: 'currency'"),
    ),
    (
        "o02",
        "other",
        "db-down",
        "app/db/pool.py",
        "psycopg2.OperationalError: could not connect to server: Connection refused",
        trace(
            "app/db/pool.py",
            "connect",
            "conn = psycopg2.connect(dsn)",
            "psycopg2.OperationalError: could not connect to server: Connection refused",
        ),
    ),
]

QUERIES = [
    (
        "q01",
        "shop",
        "currency",
        "billing/invoice.py",
        "KeyError: 'currency'",
        trace("billing/invoice.py", "invoice_currency", 'return order["currency"].upper()', "KeyError: 'currency'", 12),
    ),
    (
        "q02",
        "shop",
        "currency",
        "billing/refund.py",
        "KeyError: 'currency'",
        trace("billing/refund.py", "refund_currency", 'code = order["currency"]', "KeyError: 'currency'"),
    ),
    (
        "q03",
        "shop",
        "db-down",
        "app/db/pool.py",
        "psycopg2.OperationalError: could not connect to server: Connection refused",
        trace(
            "app/db/pool.py",
            "connect",
            "conn = psycopg2.connect(dsn)",
            "psycopg2.OperationalError: could not connect to server: Connection refused",
            14,
        ),
    ),
    (
        "q04",
        "shop",
        "db-down",
        "reports/export.py",
        "psycopg2.OperationalError: could not connect to server: Connection refused",
        trace(
            "reports/export.py",
            "export_csv",
            "rows = fetch_rows(query)",
            "psycopg2.OperationalError: could not connect to server: Connection refused",
        ),
    ),
    (
        "q05",
        "shop",
        "none-user",
        "app/notify.py",
        "AttributeError: 'NoneType' object has no attribute 'email'",
        trace(
            "app/notify.py",
            "notify",
            "send_mail(user.email)",
            "AttributeError: 'NoneType' object has no attribute 'email'",
            15,
        ),
    ),
    (
        "q06",
        "shop",
        "none-user",
        "app/sms.py",
        "AttributeError: 'NoneType' object has no attribute 'phone'",
        trace(
            "app/sms.py",
            "send_sms",
            "dial(customer.phone)",
            "AttributeError: 'NoneType' object has no attribute 'phone'",
        ),
    ),
    (
        "q07",
        "shop",
        "bad-upstream-json",
        "app/shipping.py",
        "json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)",
        trace(
            "app/shipping.py",
            "track",
            "data = resp.json()",
            "json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)",
        ),
    ),
    (
        "q08",
        "shop",
        "payment-timeout",
        "app/payments.py",
        "requests.exceptions.ReadTimeout: HTTPSConnectionPool(host='pay.example.test', port=443): Read timed out.",
        trace(
            "app/payments.py",
            "refund",
            "resp = session.post(refund_url, json=body, timeout=10)",
            "requests.exceptions.ReadTimeout: HTTPSConnectionPool(host='pay.example.test', port=443): Read timed out.",
        ),
    ),
    (
        "q09",
        "shop",
        None,
        "app/export.py",
        "PermissionError: [Errno 13] Permission denied: '/data/export.csv'",
        trace(
            "app/export.py",
            "write_file",
            "with open(path, 'w') as fh:",
            "PermissionError: [Errno 13] Permission denied: '/data/export.csv'",
        ),
    ),
    (
        "q10",
        "shop",
        None,
        "app/server.py",
        "ValueError: invalid literal for int() with base 10: ''",
        trace(
            "app/server.py",
            "server_port",
            'return int(os.environ.get("PORT", ""))',
            "ValueError: invalid literal for int() with base 10: ''",
        ),
    ),
    ("q11", "shop", None, None, "", ""),
    (
        "q12",
        "other",
        "currency",
        "billing/invoice.py",
        "KeyError: 'currency'",
        trace("billing/invoice.py", "invoice_currency", 'return order["currency"].upper()', "KeyError: 'currency'"),
    ),
]


def main() -> None:
    corpus = [
        {"id": i, "repo_name": repo, "group": group, "affected_file": f, "error_message": err, "stack_trace": tb}
        for i, repo, group, f, err, tb in CORPUS
    ]
    queries = [
        {
            "id": qid,
            "repo_name": repo,
            "affected_file": f,
            "error_message": err,
            "stack_trace": tb,
            "relevant_ids": [c["id"] for c in corpus if group and c["repo_name"] == repo and c["group"] == group],
        }
        for qid, repo, group, f, err, tb in QUERIES
    ]
    OUT.write_text(
        json.dumps({"version": "retrieval-cases-v1", "corpus": corpus, "queries": queries}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(corpus)} incidents and {len(queries)} queries to {OUT}")


if __name__ == "__main__":
    main()
