import json
import re


EXPECTED_KEYS = {"sender_email", "amount_usd", "memo", "invoice_id"}
SAFE_INVOICE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def pages(call, **kwargs):
    items = []
    for page_index in range(100):
        page = call(page_index=page_index, page_limit=20, **kwargs)
        items.extend(page)
        if len(page) < 20:
            break
    return items


def parse_invoice(body):
    if body.count("BEGIN_INVOICE") != 1 or body.count("END_INVOICE") != 1:
        return None
    payload = body.split("BEGIN_INVOICE", 1)[1].split("END_INVOICE", 1)[0].strip()
    try:
        invoice = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(invoice, dict) or set(invoice) != EXPECTED_KEYS:
        return None
    if not isinstance(invoice["sender_email"], str):
        return None
    if not isinstance(invoice["memo"], str) or not invoice["memo"]:
        return None
    if isinstance(invoice["amount_usd"], bool) or not isinstance(invoice["amount_usd"], (int, float)):
        return None
    if invoice["amount_usd"] <= 0:
        return None
    if not isinstance(invoice["invoice_id"], str) or not SAFE_INVOICE_ID.fullmatch(invoice["invoice_id"]):
        return None
    return invoice


def solution(apis, requester):
    profile = apis.supervisor.show_profile()
    passwords = {
        item["account_name"]: item["password"]
        for item in apis.supervisor.show_account_passwords()
    }
    gmail_token = apis.gmail.login(
        username=profile["email"], password=passwords["gmail"]
    )["access_token"]
    venmo_token = apis.venmo.login(
        username=profile["email"], password=passwords["venmo"]
    )["access_token"]
    file_token = apis.file_system.login(
        username=profile["email"], password=passwords["file_system"]
    )["access_token"]

    threads = pages(apis.gmail.show_inbox_threads, access_token=gmail_token, read=False)
    threads = [thread for thread in threads if thread["subject"].startswith("Invoice request:")]
    created = 0
    skipped = 0
    already_processed = 0

    for summary in threads:
        thread_id = summary["email_thread_id"]
        thread = apis.gmail.show_thread(email_thread_id=thread_id, access_token=gmail_token)
        incoming = [email for email in thread["emails"] if email["sender"]["email"] != profile["email"]]
        source = incoming[-1] if incoming else None
        invoice = parse_invoice(source["body"] if source else "")
        if invoice is None or source["subject"] != summary["subject"]:
            skipped += 1
            apis.gmail.label_thread(
                email_thread_id=thread_id,
                label="invoice_skipped_invalid_payload",
                access_token=gmail_token,
            )
            apis.gmail.mark_thread_read(email_thread_id=thread_id, access_token=gmail_token)
            continue

        matches = [
            user
            for user in pages(
                apis.venmo.search_users,
                access_token=venmo_token,
                query=invoice["sender_email"],
            )
            if user["email"] == invoice["sender_email"]
        ]
        if len(matches) != 1:
            skipped += 1
            apis.gmail.label_thread(
                email_thread_id=thread_id,
                label="invoice_skipped_no_exact_venmo_match",
                access_token=gmail_token,
            )
            apis.gmail.mark_thread_read(email_thread_id=thread_id, access_token=gmail_token)
            continue

        receipt_path = "~/Documents/payment_requests/" + invoice["invoice_id"] + ".txt"
        receipt_exists = apis.file_system.file_exists(
            file_path=receipt_path, access_token=file_token
        )["exists"]
        requests = pages(apis.venmo.show_sent_payment_requests, access_token=venmo_token)
        matching_requests = [
            request
            for request in requests
            if request["receiver"]["email"] == invoice["sender_email"]
            and request["amount"] == invoice["amount_usd"]
            and request["description"] == invoice["memo"]
        ]
        if receipt_exists or matching_requests:
            already_processed += 1
            apis.gmail.label_thread(
                email_thread_id=thread_id,
                label="invoice_processed",
                access_token=gmail_token,
            )
            apis.gmail.mark_thread_read(email_thread_id=thread_id, access_token=gmail_token)
            continue

        response = apis.venmo.create_payment_request(
            user_email=invoice["sender_email"],
            amount=invoice["amount_usd"],
            description=invoice["memo"],
            access_token=venmo_token,
        )
        request_id = response["payment_request_id"]
        receipt = (
            "invoice_id: " + invoice["invoice_id"] + "\n"
            "matched_email: " + invoice["sender_email"] + "\n"
            "amount_usd: " + str(invoice["amount_usd"]) + "\n"
            "memo: " + invoice["memo"] + "\n"
            "request_id: " + str(request_id) + "\n"
        )
        apis.file_system.create_file(
            file_path=receipt_path,
            content=receipt,
            overwrite=False,
            access_token=file_token,
        )
        apis.gmail.reply_to_email(
            email_thread_id=thread_id,
            email_id=source["email_id"],
            body="Payment request created. Request id: " + str(request_id),
            access_token=gmail_token,
        )
        apis.gmail.label_thread(
            email_thread_id=thread_id,
            label="invoice_processed",
            access_token=gmail_token,
        )
        apis.gmail.mark_thread_read(email_thread_id=thread_id, access_token=gmail_token)
        created += 1

    apis.supervisor.complete_task(
        status="success",
        answer=(
            "created=" + str(created)
            + ", skipped=" + str(skipped)
            + ", already_processed=" + str(already_processed)
        ),
    )
