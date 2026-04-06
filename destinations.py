"""
Destination router — sends approved invoice data to configured destinations.
TODO: Add more ERP connectors (SAP, QuickBooks, NetSuite SDKs).
"""
import json
import os
import smtplib
from email.mime.text import MIMEText
from typing import Optional

import requests


def send_to_erp_webhook(invoice_data: dict, webhook_url: str) -> tuple[bool, str]:
    """POST invoice JSON to an ERP webhook URL."""
    try:
        r = requests.post(
            webhook_url,
            json=invoice_data,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        r.raise_for_status()
        return True, f"ERP responded {r.status_code}"
    except Exception as e:
        return False, str(e)


def send_slack_notification(invoice_data: dict, webhook_url: str) -> tuple[bool, str]:
    """Send invoice summary to Slack via incoming webhook."""
    try:
        inv_no = invoice_data.get("invoice_number") or "—"
        total = invoice_data.get("total_amount") or "—"
        currency = invoice_data.get("currency") or ""
        vendor = (invoice_data.get("sender") or {}).get("name") or "—"
        receiver = (invoice_data.get("receiver") or {}).get("name") or "—"

        message = {
            "text": f"✅ Invoice Approved",
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "✅ Invoice Approved"}},
                {"type": "section", "fields": [
                    {"type": "mrkdwn", "text": f"*Invoice #:*\n{inv_no}"},
                    {"type": "mrkdwn", "text": f"*Total:*\n{currency} {total}"},
                    {"type": "mrkdwn", "text": f"*From:*\n{vendor}"},
                    {"type": "mrkdwn", "text": f"*Bill To:*\n{receiver}"},
                ]},
            ],
        }
        r = requests.post(webhook_url, json=message, timeout=10)
        r.raise_for_status()
        return True, "Slack notification sent"
    except Exception as e:
        return False, str(e)


def send_email_notification(
    invoice_data: dict,
    to_email: str,
    smtp_host: str = "smtp.gmail.com",
    smtp_port: int = 587,
    smtp_user: Optional[str] = None,
    smtp_password: Optional[str] = None,
) -> tuple[bool, str]:
    """Send invoice summary via email using SMTP."""
    try:
        inv_no = invoice_data.get("invoice_number") or "—"
        total = invoice_data.get("total_amount") or "—"
        currency = invoice_data.get("currency") or ""
        vendor = (invoice_data.get("sender") or {}).get("name") or "—"
        receiver = (invoice_data.get("receiver") or {}).get("name") or "—"

        body = f"""Invoice Approved ✅

Invoice #: {inv_no}
Vendor: {vendor}
Bill To: {receiver}
Total: {currency} {total}

This invoice has been approved and processed.
"""
        msg = MIMEText(body, 'plain')
        msg["Subject"] = f"Invoice Approved: #{inv_no} — {vendor}"
        msg["From"] = smtp_user or to_email
        msg["To"] = to_email

        # Use env SMTP credentials if not provided
        smtp_user = smtp_user or os.environ.get("SMTP_USER")
        smtp_password = smtp_password or os.environ.get("SMTP_PASSWORD")

        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            if smtp_user and smtp_password:
                server.login(smtp_user, smtp_password)
            server.send_message(msg)
        return True, f"Email sent to {to_email}"
    except Exception as e:
        return False, f"Email failed: {str(e)}"


def route_approved_invoice(invoice_data: dict, settings: dict) -> dict:
    """
    Route approved invoice to all configured destinations.
    Supports multiple ERPs, emails, and Slack webhooks.
    Returns a dict of destination -> list of results.
    """
    results = {"erp": [], "slack": [], "email": []}

    for url in settings.get("erp_webhooks") or []:
        ok, msg = send_to_erp_webhook(invoice_data, url)
        results["erp"].append({"url": url, "success": ok, "message": msg})

    for url in settings.get("slack_webhooks") or []:
        ok, msg = send_slack_notification(invoice_data, url)
        results["slack"].append({"url": url, "success": ok, "message": msg})

    for email in settings.get("notification_emails") or []:
        ok, msg = send_email_notification(invoice_data, email)
        results["email"].append({"email": email, "success": ok, "message": msg})

    return results
