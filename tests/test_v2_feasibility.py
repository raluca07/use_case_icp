import json
from types import SimpleNamespace

from rdr.v2_feasibility import (
    FIXTURE_PATH,
    _invoice_body,
    load_fixture,
    sha256_file,
    snapshot_task_state,
)


def test_fixture_is_versioned_fake_data():
    fixture = load_fixture()
    assert fixture["fixture_id"] == "invoice-v1"
    assert len(fixture["invoices"]) == 2
    assert all(item["sender_email"].endswith("@example.com") for item in fixture["invoices"])
    assert fixture["unmatched_invoice"]["sender_email"].endswith("@example.com")
    assert fixture["similar_nonmatch"]["email"].endswith("@example.com")
    assert len(sha256_file(FIXTURE_PATH)) == 64


def test_invoice_fields_are_confined_to_delimited_json():
    invoice = load_fixture()["invoices"][0]
    body = _invoice_body(invoice)
    payload = body.split("BEGIN_INVOICE\n", 1)[1].split("\nEND_INVOICE", 1)[0]
    assert json.loads(payload) == {
        "amount_usd": invoice["amount_usd"],
        "invoice_id": invoice["invoice_id"],
        "memo": invoice["memo"],
        "sender_email": invoice["sender_email"],
    }


def test_task_state_scope_comes_from_fixture_not_execution_writes():
    fixture = load_fixture()
    invoice = fixture["invoices"][0]
    subject = "Invoice request: " + invoice["subject_suffix"]

    def page(values):
        return lambda page_index, page_limit, **kwargs: values if page_index == 0 else []

    def login(username, password):
        return {"access_token": "token"}

    gmail = SimpleNamespace(
        login=login,
        show_inbox_threads=page([
            {"email_thread_id": 1, "subject": subject},
            {"email_thread_id": 2, "subject": "Unrelated message"},
        ]),
        show_thread=lambda email_thread_id, access_token: {"emails": [{"thread": email_thread_id}]},
    )
    venmo = SimpleNamespace(
        login=login,
        search_users=lambda page_index, page_limit, query, access_token: (
            [{"email": query}] if page_index == 0 else []
        ),
        show_sent_payment_requests=page([
            {"payment_request_id": 3, "receiver": {"email": invoice["sender_email"]}},
            {"payment_request_id": 4, "receiver": {"email": "outside@example.com"}},
        ]),
    )
    file_system = SimpleNamespace(
        login=login,
        file_exists=lambda file_path, access_token: {"exists": False},
        show_file=lambda file_path, access_token: {"content": "unexpected"},
    )
    supervisor = SimpleNamespace(
        show_profile=lambda: {"email": "owner@example.com"},
        show_account_passwords=lambda: [
            {"account_name": name, "password": "pw"}
            for name in ("gmail", "venmo", "file_system")
        ],
    )
    world = SimpleNamespace(apis=SimpleNamespace(
        supervisor=supervisor, gmail=gmail, venmo=venmo, file_system=file_system
    ))

    state = snapshot_task_state(world, fixture)

    assert [item["summary"]["subject"] for item in state["gmail_threads"]] == [subject]
    assert [item["payment_request_id"] for item in state["relevant_payment_requests"]] == [3]
    assert set(state["venmo_users_by_email"]) == {
        invoice["sender_email"] for invoice in [*fixture["invoices"], fixture["unmatched_invoice"]]
    } | {fixture["similar_nonmatch"]["email"]}
    assert all(content is None for content in state["receipt_files"].values())
