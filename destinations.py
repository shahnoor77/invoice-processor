"""
Destination router — builds structured invoice payload and sends to all configured destinations.
All destinations fire in parallel threads.
"""
import json
import os
import smtplib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import requests


def build_invoice_payload(invoice_data: dict, approval_status: str = "APPROVED", approved_by: str = None) -> dict:
    """
    Build a comprehensive, structured payload from extracted invoice data.
    This is what gets sent to ERP webhooks, Slack, and email.
    """
    s = invoice_data.get("sender") or {}
    r = invoice_data.get("receiver") or {}
    sb = s.get("bank") or {}
    rb = r.get("bank") or {}
    items = invoice_data.get("line_items") or []

    return {
        "event": "invoice.approved",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "approved_by": approved_by,
        "approval_status": approval_status,

        # Invoice metadata
        "invoice": {
            "invoice_number": invoice_data.get("invoice_number"),
            "invoice_date": invoice_data.get("invoice_date"),
            "due_date": invoice_data.get("due_date"),
            "delivery_date": invoice_data.get("delivery_date"),
            "purchase_order": invoice_data.get("purchase_order"),
            "reference": invoice_data.get("reference"),
            "payment_terms": invoice_data.get("payment_terms"),
            "payment_method": invoice_data.get("payment_method"),
        },

        # Sender / Vendor / Seller
        "sender": {
            "name": s.get("name"),
            "address": s.get("address"),
            "city": s.get("city"),
            "state": s.get("state"),
            "zip": s.get("zip"),
            "country": s.get("country"),
            "phone": s.get("phone"),
            "email": s.get("email"),
            "website": s.get("website"),
            "tax_id": s.get("tax_id"),
            "vat_number": s.get("vat_number"),
            "registration_number": s.get("registration_number"),
            "bank": {
                "bank_name": sb.get("bank_name"),
                "account_holder": sb.get("account_holder"),
                "account_number": sb.get("account_number"),
                "iban": sb.get("iban"),
                "swift_bic": sb.get("swift_bic"),
                "routing_number": sb.get("routing_number"),
                "sort_code": sb.get("sort_code"),
                "branch": sb.get("branch"),
                "bank_address": sb.get("bank_address"),
            },
        },

        # Receiver / Buyer / Client
        "receiver": {
            "name": r.get("name"),
            "address": r.get("address"),
            "city": r.get("city"),
            "state": r.get("state"),
            "zip": r.get("zip"),
            "country": r.get("country"),
            "phone": r.get("phone"),
            "email": r.get("email"),
            "tax_id": r.get("tax_id"),
            "vat_number": r.get("vat_number"),
            "bank": {
                "bank_name": rb.get("bank_name"),
                "account_holder": rb.get("account_holder"),
                "account_number": rb.get("account_number"),
                "iban": rb.get("iban"),
                "swift_bic": rb.get("swift_bic"),
                "routing_number": rb.get("routing_number"),
                "sort_code": rb.get("sort_code"),
                "branch": rb.get("branch"),
            },
        },

        # Line items
        "line_items": [
            {
                "description": item.get("description"),
                "quantity": item.get("quantity"),
                "unit": item.get("unit"),
                "unit_price": item.get("unit_price"),
                "discount_percent": item.get("discount_percent"),
                "discount_amount": item.get("discount_amount"),
                "tax_percent": item.get("tax_percent"),
                "tax_amount": item.get("tax_amount"),
                "total": item.get("total"),
            }
            for item in items
        ],

        # Financial summary
        "financials": {
            "currency": invoice_data.get("currency"),
            "exchange_rate": invoice_data.get("exchange_rate"),
            "subtotal": invoice_data.get("subtotal"),
            "discount_total": invoice_data.get("discount_total"),
            "discount_percent": invoice_data.get("discount_percent"),
            "tax_type": invoice_data.get("tax_type"),
            "tax_rate": invoice_data.get("tax_rate"),
            "tax_amount": invoice_data.get("tax_amount"),
            "shipping": invoice_data.get("shipping"),
            "handling": invoice_data.get("handling"),
            "other_charges": invoice_data.get("other_charges"),
            "total_amount": invoice_data.get("total_amount"),
            "amount_paid": invoice_data.get("amount_paid"),
            "amount_due": invoice_data.get("amount_due"),
            "deposit": invoice_data.get("deposit"),
        },

        # Additional info
        "notes": invoice_data.get("notes"),
        "terms_and_conditions": invoice_data.get("terms_and_conditions"),
        "ocr_confidence": invoice_data.get("confidence"),
    }


def send_to_erp_webhook(payload: dict, webhook: dict) -> tuple[bool, str]:
    """
    POST structured invoice payload to an ERP/webhook URL.
    Supports auth: None, Bearer Token, API Key, Basic Auth, HMAC.
    """
    url = webhook.get("url") if isinstance(webhook, dict) else webhook
    method = (webhook.get("method", "POST") if isinstance(webhook, dict) else "POST").upper()
    auth_type = webhook.get("auth_type", "None") if isinstance(webhook, dict) else "None"
    auth_creds = webhook.get("auth_credentials") or {}
    content_type = webhook.get("content_type", "application/json") if isinstance(webhook, dict) else "application/json"
    timeout = webhook.get("timeout_seconds", 30) if isinstance(webhook, dict) else 30
    custom_headers = webhook.get("custom_headers") or {}

    # Build headers
    headers = {"Content-Type": content_type, **custom_headers}

    # Apply authentication
    if auth_type == "Bearer Token":
        token = auth_creds.get("bearer_token", "")
        headers["Authorization"] = f"Bearer {token}"
    elif auth_type == "API Key":
        key_name = auth_creds.get("api_key_name", "X-API-Key")
        key_value = auth_creds.get("api_key_value", "")
        headers[key_name] = key_value
    elif auth_type == "HMAC Secret":
        import hashlib, hmac as hmac_lib
        secret = auth_creds.get("hmac_secret", "").encode()
        algo = auth_creds.get("hmac_algo", "SHA256").lower().replace("-", "")
        body = json.dumps(payload).encode()
        sig = hmac_lib.new(secret, body, getattr(hashlib, algo, hashlib.sha256)).hexdigest()
        headers["X-Signature"] = f"{algo}={sig}"

    # Apply payload template if configured
    payload_template = webhook.get("payload_template") if isinstance(webhook, dict) else None
    if payload_template:
        try:
            # Simple template substitution for common fields
            body_str = payload_template
            flat = {
                "invoice.id": payload.get("invoice", {}).get("invoice_number", ""),
                "invoice.number": payload.get("invoice", {}).get("invoice_number", ""),
                "invoice.total": str(payload.get("financials", {}).get("total_amount", "")),
                "invoice.amount_due": str(payload.get("financials", {}).get("amount_due", "")),
                "invoice.currency": payload.get("financials", {}).get("currency", ""),
                "invoice.date": payload.get("invoice", {}).get("invoice_date", ""),
                "invoice.due_date": payload.get("invoice", {}).get("due_date", ""),
                "invoice.status": payload.get("approval_status", ""),
                "vendor.name": payload.get("sender", {}).get("name", ""),
                "client.name": payload.get("receiver", {}).get("name", ""),
            }
            for k, v in flat.items():
                body_str = body_str.replace(f"{{{{{k}}}}}", str(v))
            send_body = body_str
            is_json = False
        except Exception:
            send_body = payload
            is_json = True
    else:
        send_body = payload
        is_json = True

    try:
        auth = None
        if auth_type == "Basic Auth":
            auth = (auth_creds.get("basic_user", ""), auth_creds.get("basic_pass", ""))

        if is_json:
            r = requests.request(method, url, json=send_body, headers=headers, auth=auth, timeout=timeout)
        else:
            r = requests.request(method, url, data=send_body, headers=headers, auth=auth, timeout=timeout)

        r.raise_for_status()
        return True, f"HTTP {r.status_code} — {r.text[:200]}"
    except requests.exceptions.Timeout:
        return False, f"Timeout after {timeout}s"
    except requests.exceptions.ConnectionError as e:
        return False, f"Connection error: {str(e)[:200]}"
    except Exception as e:
        return False, str(e)[:300]


def send_slack_notification(payload: dict, webhook_url: str) -> tuple[bool, str]:
    """Send formatted invoice summary to Slack."""
    inv = payload.get("invoice", {})
    fin = payload.get("financials", {})
    sender = payload.get("sender", {})
    receiver = payload.get("receiver", {})
    cur = fin.get("currency", "")
    line_items = payload.get("line_items") or []

    def fmt(v):
        return str(v).strip() if v not in (None, "") else "—"

    def fmt_date(v):
        if not v:
            return "—"
        try:
            dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return str(v)

    def fmt_money(v):
        if v in (None, ""):
            return "—"
        try:
            prefix = f"{cur} " if cur else ""
            return f"{prefix}{float(v):,.2f}"
        except Exception:
            return str(v)

    approved_by = fmt(payload.get("approved_by"))
    approved_on = fmt_date(payload.get("timestamp"))
    inv_number = fmt(inv.get("invoice_number"))

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Invoice Approved: {inv_number}"}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"This invoice was approved by *{approved_by}* on *{approved_on}*.\n"
                    f"*From:* {fmt(sender.get('name'))}  |  *Bill To:* {fmt(receiver.get('name'))}"
                ),
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Invoice Key Details*"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Invoice Number*\n{inv_number}"},
                {"type": "mrkdwn", "text": f"*Invoice Date*\n{fmt(inv.get('invoice_date'))}"},
                {"type": "mrkdwn", "text": f"*Due Date*\n{fmt(inv.get('due_date'))}"},
                {"type": "mrkdwn", "text": f"*Purchase Order*\n{fmt(inv.get('purchase_order'))}"},
                {"type": "mrkdwn", "text": f"*Reference*\n{fmt(inv.get('reference'))}"},
                {"type": "mrkdwn", "text": f"*Payment Terms*\n{fmt(inv.get('payment_terms'))}"},
                {"type": "mrkdwn", "text": f"*Payment Method*\n{fmt(inv.get('payment_method'))}"},
                {"type": "mrkdwn", "text": f"*Currency*\n{fmt(fin.get('currency'))}"},
            ],
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Financial Summary*"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Subtotal*\n{fmt_money(fin.get('subtotal'))}"},
                {"type": "mrkdwn", "text": f"*Discount*\n{fmt_money(fin.get('discount_total'))}"},
                {"type": "mrkdwn", "text": f"*Tax*\n{fmt_money(fin.get('tax_amount'))} ({fmt(fin.get('tax_rate'))}%)"},
                {"type": "mrkdwn", "text": f"*Shipping*\n{fmt_money(fin.get('shipping'))}"},
                {"type": "mrkdwn", "text": f"*Total Amount*\n{fmt_money(fin.get('total_amount'))}"},
                {"type": "mrkdwn", "text": f"*Amount Paid*\n{fmt_money(fin.get('amount_paid'))}"},
                {"type": "mrkdwn", "text": f"*Amount Due*\n{fmt_money(fin.get('amount_due'))}"},
                {"type": "mrkdwn", "text": f"*Status*\n{fmt(payload.get('approval_status'))}"},
            ],
        },
    ]

    if line_items:
        lines = []
        for idx, item in enumerate(line_items[:5], start=1):
            desc = fmt(item.get("description"))
            qty = fmt(item.get("quantity"))
            total = fmt_money(item.get("total"))
            lines.append(f"{idx}. {desc} (Qty: {qty}) - {total}")

        if len(line_items) > 5:
            lines.append(f"...and {len(line_items) - 5} more item(s)")

        blocks.extend([
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Line Items*\n" + "\n".join(lines),
                },
            },
        ])

    # Add bank details if present
    sender_bank = sender.get("bank", {})
    if sender_bank.get("bank_name") or sender_bank.get("iban"):
        bank_text = f"*Payment Details*\n*Bank:* {fmt(sender_bank.get('bank_name'))}"
        if sender_bank.get("account_number"):
            bank_text += f"\n*Account:* {sender_bank['account_number']}"
        if sender_bank.get("iban"):
            bank_text += f"\n*IBAN:* {sender_bank['iban']}"
        if sender_bank.get("swift_bic"):
            bank_text += f"\n*SWIFT:* {sender_bank['swift_bic']}"
        blocks.append({"type": "divider"})
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": bank_text}})

    if payload.get("notes"):
        blocks.append({"type": "divider"})
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Notes:*\n{payload['notes']}"}})

    try:
        fallback_text = (
            f"Invoice {inv_number} approved by {approved_by} on {approved_on}. "
            f"Amount due: {fmt_money(fin.get('amount_due'))}."
        )
        r = requests.post(webhook_url, json={"blocks": blocks, "text": fallback_text}, timeout=10)
        r.raise_for_status()
        return True, "Slack notification sent"
    except Exception as e:
        return False, str(e)


def send_email_notification(payload: dict, to_email: str) -> tuple[bool, str]:
    """Send comprehensive invoice summary via email."""
    inv = payload.get("invoice", {})
    fin = payload.get("financials", {})
    sender_info = payload.get("sender", {})
    receiver_info = payload.get("receiver", {})
    sender_bank = sender_info.get("bank", {})
    cur = fin.get("currency", "")

    def fmt(v): return str(v) if v else "—"
    def fmt_money(v):
        if v is None: return "—"
        try: return f"{cur} {float(v):,.2f}"
        except: return str(v)

    inv_no = fmt(inv.get("invoice_number"))

    # Build HTML email
    line_items_html = ""
    for item in payload.get("line_items", []):
        line_items_html += f"""
        <tr>
            <td style="padding:8px;border-bottom:1px solid #eee;">{fmt(item.get('description'))}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;text-align:center;">{fmt(item.get('quantity'))}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;text-align:right;">{fmt_money(item.get('unit_price'))}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;text-align:right;">{fmt_money(item.get('total'))}</td>
        </tr>"""

    bank_section = ""
    if sender_bank.get("bank_name") or sender_bank.get("iban"):
        bank_section = f"""
        <h3 style="color:#1a56db;">Payment Details</h3>
        <table style="width:100%;border-collapse:collapse;">
            <tr><td style="padding:4px;color:#666;">Bank Name</td><td style="padding:4px;">{fmt(sender_bank.get('bank_name'))}</td></tr>
            <tr><td style="padding:4px;color:#666;">Account Holder</td><td style="padding:4px;">{fmt(sender_bank.get('account_holder'))}</td></tr>
            <tr><td style="padding:4px;color:#666;">Account Number</td><td style="padding:4px;">{fmt(sender_bank.get('account_number'))}</td></tr>
            <tr><td style="padding:4px;color:#666;">IBAN</td><td style="padding:4px;">{fmt(sender_bank.get('iban'))}</td></tr>
            <tr><td style="padding:4px;color:#666;">SWIFT/BIC</td><td style="padding:4px;">{fmt(sender_bank.get('swift_bic'))}</td></tr>
        </table>"""

    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;padding:20px;">
        <div style="background:#1a56db;color:white;padding:20px;border-radius:8px 8px 0 0;">
            <h1 style="margin:0;">✅ Invoice Approved</h1>
            <p style="margin:5px 0 0;">Invoice #{inv_no}</p>
        </div>
        <div style="border:1px solid #ddd;border-top:none;padding:20px;border-radius:0 0 8px 8px;">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px;">
                <div>
                    <h3 style="color:#1a56db;">From (Vendor)</h3>
                    <p><strong>{fmt(sender_info.get('name'))}</strong><br>
                    {fmt(sender_info.get('address'))}<br>
                    {fmt(sender_info.get('city'))} {fmt(sender_info.get('country'))}<br>
                    {fmt(sender_info.get('email'))}<br>
                    {fmt(sender_info.get('phone'))}</p>
                </div>
                <div>
                    <h3 style="color:#1a56db;">Bill To (Client)</h3>
                    <p><strong>{fmt(receiver_info.get('name'))}</strong><br>
                    {fmt(receiver_info.get('address'))}<br>
                    {fmt(receiver_info.get('city'))} {fmt(receiver_info.get('country'))}<br>
                    {fmt(receiver_info.get('email'))}</p>
                </div>
            </div>
            <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
                <tr style="background:#f0f7ff;">
                    <th style="padding:10px;text-align:left;">Description</th>
                    <th style="padding:10px;text-align:center;">Qty</th>
                    <th style="padding:10px;text-align:right;">Unit Price</th>
                    <th style="padding:10px;text-align:right;">Total</th>
                </tr>
                {line_items_html}
            </table>
            <div style="text-align:right;margin-bottom:20px;">
                <table style="margin-left:auto;border-collapse:collapse;">
                    <tr><td style="padding:4px 12px;color:#666;">Subtotal</td><td style="padding:4px 12px;">{fmt_money(fin.get('subtotal'))}</td></tr>
                    <tr><td style="padding:4px 12px;color:#666;">Discount</td><td style="padding:4px 12px;">{fmt_money(fin.get('discount_total'))}</td></tr>
                    <tr><td style="padding:4px 12px;color:#666;">Tax ({fmt(fin.get('tax_rate'))}%)</td><td style="padding:4px 12px;">{fmt_money(fin.get('tax_amount'))}</td></tr>
                    <tr><td style="padding:4px 12px;color:#666;">Shipping</td><td style="padding:4px 12px;">{fmt_money(fin.get('shipping'))}</td></tr>
                    <tr style="border-top:2px solid #1a56db;font-weight:bold;">
                        <td style="padding:8px 12px;">Total</td><td style="padding:8px 12px;color:#1a56db;">{fmt_money(fin.get('total_amount'))}</td>
                    </tr>
                    <tr><td style="padding:4px 12px;color:#666;">Amount Paid</td><td style="padding:4px 12px;">{fmt_money(fin.get('amount_paid'))}</td></tr>
                    <tr style="background:#fef9c3;"><td style="padding:6px 12px;font-weight:bold;">Amount Due</td><td style="padding:6px 12px;font-weight:bold;">{fmt_money(fin.get('amount_due'))}</td></tr>
                </table>
            </div>
            {bank_section}
            {f'<p style="color:#666;font-size:13px;"><strong>Notes:</strong> {payload["notes"]}</p>' if payload.get("notes") else ""}
            <p style="color:#999;font-size:12px;margin-top:20px;">Approved by {fmt(payload.get('approved_by'))} on {payload.get('timestamp', '')[:10]}</p>
        </div>
    </body></html>"""

    try:
        smtp_user = os.environ.get("SMTP_USER")
        smtp_password = os.environ.get("SMTP_PASSWORD")

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Invoice Approved: #{inv_no} — {fmt(sender_info.get('name'))}"
        msg["From"] = smtp_user or to_email
        msg["To"] = to_email
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as server:
            server.ehlo()
            server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return True, f"Email sent to {to_email}"
    except Exception as e:
        return False, f"Email failed: {str(e)}"


def route_approved_invoice(invoice_data: dict, settings: dict, approved_by: str = None) -> dict:
    """
    Build payload and route to all configured destinations in parallel.
    """
    # Build the comprehensive payload once
    payload = build_invoice_payload(invoice_data, approval_status="APPROVED", approved_by=approved_by)

    results = {"erp": [], "slack": [], "email": []}
    tasks = []

    # ERP/generic webhooks — send full structured payload
    for webhook in settings.get("erp_webhooks") or []:
        if isinstance(webhook, str):
            webhook = {"url": webhook, "method": "POST", "auth_type": "None"}
        tasks.append(("erp", webhook.get("url", ""), lambda w=webhook: send_to_erp_webhook(payload, w)))

    # Slack webhooks — send formatted message
    for url in settings.get("slack_webhooks") or []:
        tasks.append(("slack", url, lambda u=url: send_slack_notification(payload, u)))

    # Email notifications — send HTML email
    for email_addr in settings.get("notification_emails") or []:
        tasks.append(("email", email_addr, lambda e=email_addr: send_email_notification(payload, e)))

    if not tasks:
        return {"payload": payload, "erp": [], "slack": [], "email": [], "note": "No destinations configured"}

    # Fire all in parallel
    with ThreadPoolExecutor(max_workers=min(len(tasks), 10), thread_name_prefix="dest") as executor:
        future_to_task = {executor.submit(fn): (dest_type, dest_id) for dest_type, dest_id, fn in tasks}
        for future in as_completed(future_to_task):
            dest_type, dest_id = future_to_task[future]
            try:
                ok, msg = future.result(timeout=35)
                results[dest_type].append({"destination": dest_id, "success": ok, "message": msg})
            except Exception as e:
                results[dest_type].append({"destination": dest_id, "success": False, "message": str(e)})

    results["payload_sent"] = payload  # include payload in response for debugging
    return results
