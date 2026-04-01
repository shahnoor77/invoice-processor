#!/usr/bin/env python
import io
import json
import os
import re
import sys
import tempfile
import threading

import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
load_dotenv(override=True)

try:
    if "OPENAI_API_KEY" in st.secrets:
        os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]
except Exception:
    pass

from invoice_processing_automation_system.crew import InvoiceProcessingAutomationSystemCrew
from invoice_processing_automation_system.sheets import (
    get_processed_invoices, log_processing, save_invoice
)

st.set_page_config(page_title="Invoice Processing", page_icon="🧾", layout="wide")
st.title("🧾 Invoice Processing Automation System")
st.caption("Powered by CrewAI")

TASK_LABELS = {
    "invoice_file_detection_and_intake": ("1️⃣", "Document Intake", "File detection and text extraction"),
    "structured_data_extraction": ("2️⃣", "Data Extraction", "Structured JSON extraction from invoice"),
    "invoice_data_validation": ("3️⃣", "Validation", "Mathematical and logical validation"),
    "erp_system_integration": ("4️⃣", "ERP Integration", "Push data to ERP system"),
    "finance_team_notification": ("5️⃣", "Notification", "Notify finance team"),
}

# ── Session state init ──────────────────────────────────────────────────────
for key, default in {
    "step_outputs": [],
    "extracted_json": None,
    "validation_status": "",
    "run_result": None,
    "run_error": None,
    "approval_done": False,
    "file_name": "",
    "phase": "idle",  # idle | extracting | awaiting_approval | running_erp | done
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ── Helpers ─────────────────────────────────────────────────────────────────

def verify_and_fix_totals(inv: dict) -> dict:
    """
    Verify line item totals and grand total using Python arithmetic.
    Flags mismatches but does NOT overwrite values from the invoice —
    only adds a 'math_warnings' field so the user can see discrepancies.
    """
    warnings = []

    def to_float(v):
        try:
            return float(str(v).replace(",", "").strip())
        except Exception:
            return None

    # Check each line item: quantity * unit_price should equal total
    items = inv.get("line_items") or []
    for i, item in enumerate(items):
        qty = to_float(item.get("quantity"))
        price = to_float(item.get("unit_price"))
        total = to_float(item.get("total"))
        if qty and price and total:
            expected = round(qty * price, 2)
            if abs(expected - total) > 0.02:
                warnings.append(f"Line item {i+1} '{item.get('description')}': {qty} × {price} = {expected}, but total shows {total}")

    # Check subtotal = sum of line item totals
    if items:
        line_sum = sum(to_float(i.get("total")) or 0 for i in items)
        subtotal = to_float(inv.get("subtotal"))
        if subtotal and abs(line_sum - subtotal) > 0.02:
            warnings.append(f"Subtotal mismatch: line items sum to {round(line_sum,2)}, but subtotal shows {subtotal}")

    # Check total = subtotal + tax + shipping - discount
    subtotal = to_float(inv.get("subtotal")) or 0
    tax = to_float(inv.get("tax_amount")) or 0
    shipping = to_float(inv.get("shipping")) or 0
    discount = to_float(inv.get("discount_total")) or 0
    total = to_float(inv.get("total_amount"))
    if total and subtotal:
        expected_total = round(subtotal + tax + shipping - discount, 2)
        if abs(expected_total - total) > 0.02:
            warnings.append(f"Total mismatch: {subtotal} + {tax} (tax) + {shipping} (shipping) - {discount} (discount) = {expected_total}, but total shows {total}")

    if warnings:
        inv["math_warnings"] = warnings

    return inv


def parse_json_from_text(text: str):
    if not text:
        return None
    # Try direct parse
    try:
        return json.loads(text.strip())
    except Exception:
        pass
    # Try extracting from markdown code block
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    # Try finding the largest JSON object in the text
    match = re.search(r"(\{[\s\S]*\})", text)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    return None


def render_invoice_card(inv: dict):
    # Sender / Receiver
    sender = inv.get("sender") or inv.get("vendor_info") or {}
    receiver = inv.get("receiver") or {}
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Sender (Vendor)**")
        st.write(sender.get("name") or "—")
        st.write(sender.get("address") or "—")
        st.write(f"{sender.get('city') or ''} {sender.get('country') or ''}".strip() or "—")
        st.write(sender.get("phone") or "—")
        st.write(sender.get("email") or "—")
        if sender.get("tax_id"):
            st.write(f"Tax ID: {sender['tax_id']}")
    with col2:
        st.markdown("**Receiver (Bill-To)**")
        st.write(receiver.get("name") or "—")
        st.write(receiver.get("address") or "—")
        st.write(f"{receiver.get('city') or ''} {receiver.get('country') or ''}".strip() or "—")
        st.write(receiver.get("phone") or "—")
        st.write(receiver.get("email") or "—")

    st.divider()

    # Invoice details
    d1, d2, d3, d4 = st.columns(4)
    d1.write(f"**Invoice #:** {inv.get('invoice_number') or '—'}")
    d2.write(f"**Date:** {inv.get('invoice_date') or '—'}")
    d3.write(f"**Due:** {inv.get('due_date') or '—'}")
    d4.write(f"**PO:** {inv.get('purchase_order') or '—'}")

    p1, p2, p3 = st.columns(3)
    p1.write(f"**Terms:** {inv.get('payment_terms') or '—'}")
    p2.write(f"**Currency:** {inv.get('currency') or '—'}")
    conf = inv.get("confidence", "")
    p3.write(f"**Confidence:** {'✅ HIGH' if conf == 'HIGH' else '⚠️ LOW' if conf == 'LOW' else '—'}")

    # Line items
    items = inv.get("line_items") or []
    if items:
        st.markdown("**Line Items**")
        import pandas as pd
        st.dataframe(pd.DataFrame(items).astype(str), use_container_width=True)

    st.divider()

    # Totals
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Subtotal", inv.get("subtotal") or "—")
    c2.metric("Discount", inv.get("discount_total") or "—")
    c3.metric("Tax", f"{inv.get('tax_amount') or '—'} ({inv.get('tax_rate') or '—'}%)")
    c4.metric("Shipping", inv.get("shipping") or "—")
    c5.metric("Total", inv.get("total_amount") or "—")

    a1, a2 = st.columns(2)
    a1.metric("Amount Paid", inv.get("amount_paid") or "—")
    a2.metric("Amount Due", inv.get("amount_due") or "—")

    if inv.get("notes"):
        st.info(f"Notes: {inv['notes']}")
    if inv.get("bank_details"):
        st.info(f"Bank: {inv['bank_details']}")
    if inv.get("math_warnings"):
        st.warning("⚠️ Math verification found discrepancies — check OCR text for misread numbers:")
        for w in inv["math_warnings"]:
            st.warning(f"• {w}")
    with st.expander("Raw JSON"):
        st.json(inv)


def run_extraction_crew(inputs, step_outputs, result_holder, task_callback):
    # Ensure env vars are loaded in this thread
    from dotenv import load_dotenv
    load_dotenv(override=True)

    class StreamCapture(io.StringIO):
        def __init__(self):
            super().__init__()
            self._log = []
            self._orig = sys.stdout
        def write(self, text):
            self._orig.write(text)
            if text.strip():
                self._log.append(text)
            return len(text)
        def flush(self):
            self._orig.flush()
        def get_log(self):
            return "\n".join(self._log)

    capture = StreamCapture()
    old = sys.stdout
    sys.stdout = capture
    try:
        crew = InvoiceProcessingAutomationSystemCrew()
        crew.set_task_callback(task_callback)
        result = crew.crew().kickoff(inputs=inputs)
        result_holder["result"] = result
        result_holder["logs"] = capture.get_log()
    except Exception as e:
        result_holder["error"] = str(e)
        result_holder["logs"] = capture.get_log()
    finally:
        sys.stdout = old


# ════════════════════════════════════════════════════════════════════════════
# TABS
# ════════════════════════════════════════════════════════════════════════════
tab_upload, tab_history = st.tabs(["📤 Process Invoice", "📋 Processed Invoices"])

# ── TAB 1: Process Invoice ───────────────────────────────────────────────────
with tab_upload:

    saved_paths = []
    upload_dir = None

    uploaded_files = st.file_uploader(
        "Upload Invoice Files (PDF, PNG, JPG)",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )
    if uploaded_files:
        upload_dir = tempfile.mkdtemp(prefix="invoices_")
        for uf in uploaded_files:
            fp = os.path.join(upload_dir, uf.name)
            with open(fp, "wb") as f:
                f.write(uf.getbuffer())
            saved_paths.append(fp)
        st.success(f"{len(saved_paths)} file(s) ready: {', '.join(os.path.basename(p) for p in saved_paths)}")

    st.divider()

    with st.form("crew_inputs"):
        col1, col2 = st.columns(2)
        with col1:
            erp_system = st.text_input("ERP System", placeholder="e.g. SAP, QuickBooks, NetSuite")
        with col2:
            notification_channel = st.text_input("Notification Channel", placeholder="e.g. email, Slack #finance")
        extra_prompt = st.text_area("Additional Instructions (optional)", height=80)
        submitted = st.form_submit_button("🚀 Run Invoice Processing", use_container_width=True)

    # ── Phase: Run extraction ────────────────────────────────────────────────
    if submitted:
        if not saved_paths or not erp_system or not notification_channel:
            st.error("Please upload at least one file and fill in all required fields.")
        else:
            # Reset state for new run
            st.session_state.step_outputs = []
            st.session_state.extracted_json = None
            st.session_state.validation_status = ""
            st.session_state.run_result = None
            st.session_state.run_error = None
            st.session_state.approval_done = False
            st.session_state.file_name = os.path.basename(saved_paths[0])
            st.session_state.phase = "extracting"

            file_list = "\n".join(saved_paths)
            intake_source = f"Directory: {upload_dir}\n\nFiles to process:\n{file_list}"
            if extra_prompt:
                intake_source += f"\n\nAdditional instructions: {extra_prompt}"

            # Run OCR directly in Python — pass clean text to crew to eliminate hallucination
            from invoice_processing_automation_system.tools.custom_tool import PDFTextExtractor, ImageTextExtractor
            ocr_texts = []
            pdf_tool = PDFTextExtractor()
            img_tool = ImageTextExtractor()
            with st.spinner("Extracting text from files..."):
                for fp in saved_paths:
                    ext = os.path.splitext(fp)[-1].lower()
                    result = pdf_tool._run(fp) if ext == ".pdf" else img_tool._run(fp)
                    ocr_texts.append(f"=== {os.path.basename(fp)} ===\n{result}")
            ocr_text = "\n\n".join(ocr_texts)

            # Show OCR output so user can verify before crew runs
            with st.expander("🔍 Raw OCR Text (verify numbers before processing)", expanded=False):
                st.code(ocr_text, language="text")

            st.session_state.inputs = {
                "intake_source": intake_source,
                "ocr_text": ocr_text,
                "erp_system": erp_system,
                "notification_channel": notification_channel,
            }

    # ── Run crew in background ───────────────────────────────────────────────
    if st.session_state.phase == "extracting":
        step_outputs = []
        result_holder = {"result": None, "error": None, "logs": ""}

        def task_callback(task_output):
            name = getattr(task_output, "name", "Unknown")
            agent_name = getattr(task_output, "agent", "")
            raw = getattr(task_output, "raw", str(task_output))
            step_outputs.append({"name": name, "agent": agent_name, "raw": raw})

        with st.spinner("Running crew... this may take a few minutes."):
            t = threading.Thread(
                target=run_extraction_crew,
                args=(st.session_state.inputs, step_outputs, result_holder, task_callback)
            )
            t.start()
            t.join()

        st.session_state.step_outputs = step_outputs
        st.session_state.run_result = result_holder.get("result")
        st.session_state.run_error = result_holder.get("error")
        st.session_state.logs = result_holder.get("logs", "")

        # Extract JSON from extraction step output
        for step in step_outputs:
            if step["name"] == "structured_data_extraction":
                parsed = parse_json_from_text(step["raw"])
                # Python-side math verification — correct totals if model got them wrong
                if parsed:
                    parsed = verify_and_fix_totals(parsed)
                st.session_state.extracted_json = parsed
                if not parsed:
                    st.session_state.extraction_raw = step["raw"]
            if step["name"] == "invoice_data_validation":
                raw = step["raw"].lower()
                st.session_state.validation_status = "PASS" if "pass" in raw else "FAIL"

        if result_holder.get("error"):
            st.session_state.phase = "done"
            log_processing(
                st.session_state.file_name, "ERROR",
                result_holder["error"],
                os.environ.get("MODEL", "unknown")
            )
        else:
            st.session_state.phase = "awaiting_approval"

        st.rerun()

    # ── Show step outputs ────────────────────────────────────────────────────
    if st.session_state.phase in ("awaiting_approval", "done") and st.session_state.step_outputs:
        st.subheader("📊 Agent Outputs")
        for i, step in enumerate(st.session_state.step_outputs):
            name = step["name"]
            icon, title, desc = TASK_LABELS.get(name, ("🔹", name, ""))
            with st.expander(f"{icon} Step {i+1}: {title}", expanded=(name == "structured_data_extraction")):
                st.caption(desc)
                if step["agent"]:
                    st.markdown(f"Agent: {step['agent']}")
                st.divider()
                if name == "structured_data_extraction" and st.session_state.extracted_json:
                    render_invoice_card(st.session_state.extracted_json)
                else:
                    st.markdown(step["raw"])

        if hasattr(st.session_state, "logs") and st.session_state.logs:
            with st.expander("📋 Raw Logs", expanded=False):
                st.code(st.session_state.logs, language="text")

    # ── Approval gate ────────────────────────────────────────────────────────
    if st.session_state.phase == "awaiting_approval" and not st.session_state.approval_done:
        st.divider()
        st.subheader("✅ Approval Required")
        st.info("Review the extracted invoice data above before sending to ERP and notifying the finance team.")

        if st.session_state.extracted_json:
            render_invoice_card(st.session_state.extracted_json)

        col_approve, col_reject = st.columns(2)

        with col_approve:
            if st.button("✅ Approve & Send to ERP", use_container_width=True, type="primary"):
                if st.session_state.extracted_json:
                    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
                    if sheet_id:
                        ok, err = save_invoice(
                            st.session_state.extracted_json,
                            st.session_state.file_name,
                            "APPROVED",
                        )
                        if ok:
                            st.success("Saved to Google Sheets.")
                        else:
                            st.error(f"Sheets save failed: {err}")
                    else:
                        st.info("Google Sheets not configured — skipping save. Set GOOGLE_SHEET_ID in .env to enable.")
                else:
                    st.warning("No structured JSON found — sheet not updated. Check the Data Extraction step output above.")
                st.session_state.approval_done = True
                st.session_state.phase = "done"
                st.rerun()

        with col_reject:
            reject_reason = st.text_input("Rejection reason (optional)")
            if st.button("❌ Reject", use_container_width=True):
                if st.session_state.extracted_json:
                    save_invoice(
                        st.session_state.extracted_json,
                        st.session_state.file_name,
                        f"REJECTED: {reject_reason}",
                    )
                st.session_state.approval_done = True
                st.session_state.phase = "done"
                st.warning("Invoice rejected and logged.")
                st.rerun()

    if st.session_state.phase == "done" and st.session_state.run_error:
        st.error(f"Crew execution failed: {st.session_state.run_error}")

# ── TAB 2: Processed Invoices ────────────────────────────────────────────────
with tab_history:
    st.subheader("📋 Processed Invoices")
    if not os.environ.get("GOOGLE_SHEET_ID"):
        st.info("Google Sheets not configured. Set GOOGLE_SHEET_ID and GOOGLE_CREDENTIALS_FILE in .env to enable invoice history.")
    else:
        if st.button("🔄 Refresh"):
            st.rerun()

    records = get_processed_invoices()
    if records:
        import pandas as pd
        df = pd.DataFrame(records)
        # Convert all columns to string to avoid pyarrow type conversion errors
        df = df.astype(str).replace("nan", "").replace("None", "")
        st.dataframe(df, use_container_width=True)

        # Summary metrics
        total = len(df)
        approved = len(df[df["Approval Status"].str.startswith("APPROVED")]) if "Approval Status" in df.columns else 0
        rejected = len(df[df["Approval Status"].str.startswith("REJECTED")]) if "Approval Status" in df.columns else 0
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Processed", total)
        m2.metric("Approved", approved)
        m3.metric("Rejected", rejected)
    else:
        st.info("No processed invoices yet. Run the crew to start processing.")

st.divider()
st.caption("Invoice Processing Automation System • CrewAI")
