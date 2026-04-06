#!/usr/bin/env python
import io, json, os, re, sys, tempfile, threading
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
    get_processed_invoices, save_invoice, update_approval_status, log_processing
)

st.set_page_config(page_title="Invoice Processing", page_icon="🧾", layout="wide")

# ── Global styles — light theme with blue accents ─────────────────────────────
st.markdown("""
<style>
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
@keyframes spin { to{transform:rotate(360deg)} }
</style>
""", unsafe_allow_html=True)

st.markdown('<h1 style="text-align:center;color:#1a56db;letter-spacing:2px;">🧾 Invoice Processing System</h1>', unsafe_allow_html=True)
st.markdown('<p style="text-align:center;color:#6b7280;margin-top:-10px;">Powered by CrewAI</p>', unsafe_allow_html=True)

for key, default in {
    "step_outputs": [], "extracted_json": None,
    "run_error": None, "file_name": "", "phase": "idle", "logs": "",
    "inputs": {},
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ── Helpers ───────────────────────────────────────────────────────────────────

def verify_and_fix_totals(inv):
    warnings = []
    def f(v):
        try: return float(str(v).replace(",","").strip())
        except: return None
    items = inv.get("line_items") or []
    for i, item in enumerate(items):
        q,p,t = f(item.get("quantity")), f(item.get("unit_price")), f(item.get("total"))
        if q and p and t and abs(round(q*p,2)-t) > 0.02:
            warnings.append(f"Line {i+1} '{item.get('description')}': {q}×{p}={round(q*p,2)} but shows {t}")
    sub,tax,ship,disc,tot = f(inv.get("subtotal")) or 0, f(inv.get("tax_amount")) or 0, f(inv.get("shipping")) or 0, f(inv.get("discount_total")) or 0, f(inv.get("total_amount"))
    if tot and sub:
        exp = round(sub+tax+ship-disc,2)
        if abs(exp-tot) > 0.02:
            warnings.append(f"Total: {sub}+{tax}tax+{ship}ship-{disc}disc={exp} but shows {tot}")
    if warnings: inv["math_warnings"] = warnings
    return inv

def parse_json(text):
    if not text: return None
    try: return json.loads(text.strip())
    except: pass
    for pat in [r"```(?:json)?\s*(\{.*?\})\s*```", r"(\{[\s\S]*\})"]:
        m = re.search(pat, text, re.DOTALL)
        if m:
            try: return json.loads(m.group(1))
            except: pass
    return None

def fmt(v):
    if v is None or str(v).strip() in ("","null","None"): return "—"
    return str(v)

def fmt_money(v, cur=""):
    if v is None or str(v).strip() in ("","null","None"): return "—"
    try: return f"{cur} {float(str(v).replace(',','')):.2f}".strip()
    except: return str(v)

def render_invoice(inv):
    """Render invoice as styled HTML document — blue/black theme."""
    sender = inv.get("sender") or {}
    receiver = inv.get("receiver") or {}
    items = inv.get("line_items") or []
    cur = inv.get("currency") or ""

    rows = ""
    for item in items:
        rows += f"""<tr>
            <td style="padding:10px 14px;border-bottom:1px solid #f3f4f6;">{fmt(item.get('description'))}</td>
            <td style="padding:10px 14px;border-bottom:1px solid #f3f4f6;text-align:center;">{fmt(item.get('quantity'))}</td>
            <td style="padding:10px 14px;border-bottom:1px solid #f3f4f6;text-align:right;">{fmt_money(item.get('unit_price'),cur)}</td>
            <td style="padding:10px 14px;border-bottom:1px solid #f3f4f6;text-align:right;">{fmt_money(item.get('discount'),cur)}</td>
            <td style="padding:10px 14px;border-bottom:1px solid #f3f4f6;text-align:right;color:#1a56db;font-weight:600;">{fmt_money(item.get('total'),cur)}</td>
        </tr>"""
    if not rows:
        rows = '<tr><td colspan="5" style="padding:16px;text-align:center;color:#9ca3af;">No line items extracted</td></tr>'

    po_row = f"<div style='font-size:13px;color:#6b7280;margin-top:4px;'>PO: <strong style='color:#111827;'>{fmt(inv.get('purchase_order'))}</strong></div>" if inv.get('purchase_order') and inv.get('purchase_order') != 'null' else ""
    terms_row = f"<div style='font-size:13px;color:#6b7280;margin-top:4px;'>Terms: <strong style='color:#111827;'>{fmt(inv.get('payment_terms'))}</strong></div>" if inv.get('payment_terms') and inv.get('payment_terms') != 'null' else ""
    notes_row = f"<div style='padding:14px 18px;background:#eff6ff;border-left:3px solid #1a56db;border-radius:4px;margin-bottom:12px;font-size:13px;color:#1e40af;'><strong>Notes:</strong> {fmt(inv.get('notes'))}</div>" if inv.get('notes') and inv.get('notes') != 'null' else ""
    bank_row = f"<div style='padding:14px 18px;background:#f0fdf4;border-left:3px solid #16a34a;border-radius:4px;font-size:13px;color:#166534;'><strong>Bank Details:</strong> {fmt(inv.get('bank_details'))}</div>" if inv.get('bank_details') and inv.get('bank_details') != 'null' else ""
    disc_row = f"<tr><td style='padding:6px 14px;color:#6b7280;font-size:13px;'>Discount</td><td style='padding:6px 14px;text-align:right;font-size:13px;color:#111827;'>{fmt_money(inv.get('discount_total'),cur)}</td></tr>" if inv.get('discount_total') and str(inv.get('discount_total')) not in ('null','0','0.0') else ""
    ship_row = f"<tr><td style='padding:6px 14px;color:#6b7280;font-size:13px;'>Shipping</td><td style='padding:6px 14px;text-align:right;font-size:13px;color:#111827;'>{fmt_money(inv.get('shipping'),cur)}</td></tr>" if inv.get('shipping') and str(inv.get('shipping')) not in ('null','0','0.0') else ""
    paid_row = f"<tr><td style='padding:6px 14px;color:#6b7280;font-size:13px;'>Amount Paid</td><td style='padding:6px 14px;text-align:right;font-size:13px;color:#111827;'>{fmt_money(inv.get('amount_paid'),cur)}</td></tr>" if inv.get('amount_paid') and str(inv.get('amount_paid')) not in ('null','0','0.0') else ""
    due_row = f"<tr style='background:#fef9c3;'><td style='padding:10px 14px;font-weight:700;font-size:14px;color:#854d0e;'>Amount Due</td><td style='padding:10px 14px;text-align:right;font-weight:700;font-size:14px;color:#854d0e;'>{fmt_money(inv.get('amount_due'),cur)}</td></tr>" if inv.get('amount_due') and inv.get('amount_due') != 'null' else ""
    conf = inv.get("confidence","")
    conf_badge = f"<span style='background:{'#dcfce7' if conf=='HIGH' else '#fef3c7'};color:{'#166534' if conf=='HIGH' else '#92400e'};padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;'>{'✅ HIGH' if conf=='HIGH' else '⚠️ LOW'} CONFIDENCE</span>" if conf else ""

    html = f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif;background:#ffffff;border:1px solid #e5e7eb;border-radius:12px;padding:40px;color:#111827;margin-bottom:20px;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:32px;padding-bottom:24px;border-bottom:2px solid #1a56db;">
            <div>
                <div style="font-size:32px;font-weight:800;color:#1a56db;letter-spacing:3px;">INVOICE</div>
                <div style="font-size:14px;color:#6b7280;margin-top:6px;">#{fmt(inv.get('invoice_number'))}</div>
                <div style="margin-top:10px;">{conf_badge}</div>
            </div>
            <div style="text-align:right;">
                <div style="font-size:13px;color:#6b7280;">Invoice Date: <strong style="color:#111827;">{fmt(inv.get('invoice_date'))}</strong></div>
                <div style="font-size:13px;color:#6b7280;margin-top:6px;">Due Date: <strong style="color:#1a56db;">{fmt(inv.get('due_date'))}</strong></div>
                {po_row}{terms_row}
            </div>
        </div>
        <div style="display:flex;gap:32px;margin-bottom:32px;">
            <div style="flex:1;background:#f0f7ff;border:1px solid #bfdbfe;border-radius:8px;padding:20px;">
                <div style="font-size:10px;font-weight:700;color:#1a56db;text-transform:uppercase;letter-spacing:2px;margin-bottom:12px;">FROM</div>
                <div style="font-weight:700;font-size:16px;color:#111827;">{fmt(sender.get('name'))}</div>
                <div style="font-size:13px;color:#4b5563;margin-top:6px;">{fmt(sender.get('address'))}</div>
                <div style="font-size:13px;color:#4b5563;">{fmt(sender.get('city'))} {fmt(sender.get('country'))}</div>
                {"<div style='font-size:13px;color:#4b5563;margin-top:4px;'>📞 " + fmt(sender.get('phone')) + "</div>" if sender.get('phone') and sender.get('phone') != 'null' else ""}
                {"<div style='font-size:13px;color:#4b5563;'>✉️ " + fmt(sender.get('email')) + "</div>" if sender.get('email') and sender.get('email') != 'null' else ""}
                {"<div style='font-size:12px;color:#9ca3af;margin-top:6px;'>Tax ID: " + fmt(sender.get('tax_id')) + "</div>" if sender.get('tax_id') and sender.get('tax_id') != 'null' else ""}
            </div>
            <div style="flex:1;background:#f0f7ff;border:1px solid #bfdbfe;border-radius:8px;padding:20px;">
                <div style="font-size:10px;font-weight:700;color:#1a56db;text-transform:uppercase;letter-spacing:2px;margin-bottom:12px;">BILL TO</div>
                <div style="font-weight:700;font-size:16px;color:#111827;">{fmt(receiver.get('name'))}</div>
                <div style="font-size:13px;color:#4b5563;margin-top:6px;">{fmt(receiver.get('address'))}</div>
                <div style="font-size:13px;color:#4b5563;">{fmt(receiver.get('city'))} {fmt(receiver.get('country'))}</div>
                {"<div style='font-size:13px;color:#4b5563;margin-top:4px;'>📞 " + fmt(receiver.get('phone')) + "</div>" if receiver.get('phone') and receiver.get('phone') != 'null' else ""}
                {"<div style='font-size:13px;color:#4b5563;'>✉️ " + fmt(receiver.get('email')) + "</div>" if receiver.get('email') and receiver.get('email') != 'null' else ""}
            </div>
        </div>
        <table style="width:100%;border-collapse:collapse;margin-bottom:28px;">
            <thead>
                <tr style="background:#1a56db;color:#ffffff;">
                    <th style="padding:12px 14px;text-align:left;font-size:12px;font-weight:600;letter-spacing:1px;">DESCRIPTION</th>
                    <th style="padding:12px 14px;text-align:center;font-size:12px;font-weight:600;">QTY</th>
                    <th style="padding:12px 14px;text-align:right;font-size:12px;font-weight:600;">UNIT PRICE</th>
                    <th style="padding:12px 14px;text-align:right;font-size:12px;font-weight:600;">DISCOUNT</th>
                    <th style="padding:12px 14px;text-align:right;font-size:12px;font-weight:600;">TOTAL</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
        <div style="display:flex;justify-content:flex-end;margin-bottom:24px;">
            <table style="width:300px;border-collapse:collapse;background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;">
                <tr><td style="padding:8px 14px;color:#6b7280;font-size:13px;">Subtotal</td><td style="padding:8px 14px;text-align:right;font-size:13px;color:#111827;">{fmt_money(inv.get('subtotal'),cur)}</td></tr>
                {disc_row}
                <tr><td style="padding:8px 14px;color:#6b7280;font-size:13px;">Tax ({fmt(inv.get('tax_rate'))}%)</td><td style="padding:8px 14px;text-align:right;font-size:13px;color:#111827;">{fmt_money(inv.get('tax_amount'),cur)}</td></tr>
                {ship_row}
                <tr style="border-top:2px solid #1a56db;background:#eff6ff;"><td style="padding:12px 14px;font-weight:700;font-size:16px;color:#1a56db;">TOTAL</td><td style="padding:12px 14px;text-align:right;font-weight:700;font-size:16px;color:#1a56db;">{fmt_money(inv.get('total_amount'),cur)}</td></tr>
                {paid_row}{due_row}
            </table>
        </div>
        {notes_row}{bank_row}
        <div style="margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb;font-size:11px;color:#9ca3af;text-align:center;">
            Invoice Processing Automation System • CrewAI
        </div>
    </div>"""
    st.html(html)
    if inv.get("math_warnings"):
        st.warning("⚠️ Math discrepancies detected:")
        for w in inv["math_warnings"]:
            st.caption(f"• {w}")
    with st.expander("Raw JSON"):
        st.json(inv)

def run_extraction_crew(inputs, step_outputs, result_holder, task_callback):
    from dotenv import load_dotenv
    load_dotenv(override=True)
    class StreamCapture(io.StringIO):
        def __init__(self):
            super().__init__(); self._log=[]; self._orig=sys.stdout
        def write(self, text):
            self._orig.write(text)
            if text.strip(): self._log.append(text)
            return len(text)
        def flush(self): self._orig.flush()
        def get_log(self): return "\n".join(self._log)
    capture = StreamCapture(); old = sys.stdout; sys.stdout = capture
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

# ── TAB 1 ─────────────────────────────────────────────────────────────────────
with tab_upload:

    if st.session_state.phase == "idle":
        saved_paths = []
        upload_dir = None

        input_method = st.radio("Select Input Method", ["Upload Files", "Fetch from Gmail API"], horizontal=True)

        if input_method == "Upload Files":
            uploaded_files = st.file_uploader(
                "Upload Invoice Files (PDF, PNG, JPG)",
                type=["pdf", "png", "jpg", "jpeg"],
                accept_multiple_files=True,
            )
            if uploaded_files:
                upload_dir = tempfile.mkdtemp(prefix="invoices_")
                for uf in uploaded_files:
                    fp = os.path.join(upload_dir, uf.name)
                    with open(fp, "wb") as f: f.write(uf.getbuffer())
                    saved_paths.append(fp)
                st.success(f"{len(saved_paths)} file(s) ready")
        else:
            with st.expander("📧 Gmail API Settings", expanded=True):
                col1, col2 = st.columns(2)
                with col1:
                    max_emails = st.number_input("Max Emails to Check", value=5, min_value=1, max_value=50)
                with col2:
                    query_filter = st.text_input("Gmail Query", value="in:inbox is:unread")
                
                if st.button("Fetch Invoices"):
                    with st.spinner("Connecting to Gmail API and downloading invoices..."):
                        try:
                            from invoice_processing_automation_system.fetch_latest_emails import fetch_latest_invoice_attachments
                            results = fetch_latest_invoice_attachments(
                                max_results=max_emails,
                                query=query_filter
                            )
                            if not results:
                                st.warning("No invoices found.")
                            st.session_state["email_fetch_results"] = results
                        except Exception as e:
                            st.error(f"Error fetching invoices: {str(e)}")
            
            if st.session_state.get("email_fetch_results"):
                st.markdown("#### Downloaded Email Attachments")
                selected_attachments = []
                for idx, path in enumerate(st.session_state["email_fetch_results"]):
                    if isinstance(path, str) and os.path.exists(path):
                        file_name = os.path.basename(path)
                        if st.checkbox(f"📎 {file_name}", key=f"att_gmail_{idx}", value=True):
                            selected_attachments.append(path)
                
                if selected_attachments:
                    saved_paths = selected_attachments
                    upload_dir = "Gmail Fetch Temp Dir"
                    st.success(f"{len(saved_paths)} attachment(s) selected")

        st.divider()
        with st.form("crew_inputs"):
            c1, c2 = st.columns(2)
            with c1: erp_system = st.text_input("ERP System", placeholder="SAP, QuickBooks, NetSuite")
            with c2: notification_channel = st.text_input("Notification Channel", placeholder="email, Slack #finance")
            extra_prompt = st.text_area("Additional Instructions (optional)", height=60)
            submitted = st.form_submit_button("🚀 Process Invoice", use_container_width=True)

        if submitted:
            if not saved_paths or not erp_system or not notification_channel:
                st.error("Please upload a file and fill in all fields.")
            else:
                st.session_state.step_outputs = []
                st.session_state.extracted_json = None
                st.session_state.run_error = None
                st.session_state.file_name = ", ".join([os.path.basename(p) for p in saved_paths][:3]) + ("..." if len(saved_paths) > 3 else "")
                st.session_state.phase = "extracting"

                file_list = "\n".join(saved_paths)
                intake_source = f"Directory: {upload_dir}\n\nFiles to process:\n{file_list}"
                if extra_prompt: intake_source += f"\n\nAdditional instructions: {extra_prompt}"

                from invoice_processing_automation_system.tools.custom_tool import PDFTextExtractor, ImageTextExtractor, extract_image_with_llava
                pdf_tool, img_tool = PDFTextExtractor(), ImageTextExtractor()
                ocr_texts = []
                ollama_url = os.environ.get("OLLAMA_BASE_URL", "http://110.39.187.178:11434")
                with st.spinner("Reading invoice..."):
                    for fp in saved_paths:
                        ext = os.path.splitext(fp)[-1].lower()
                        if ext == ".pdf":
                            result = pdf_tool._run(fp)
                        else:
                            # Use LLaVA vision model for images — no OCR needed
                            result = extract_image_with_llava(fp, ollama_url)
                            # Fallback to Tesseract if LLaVA fails
                            if result.startswith("Error"):
                                result = img_tool._run(fp)
                        ocr_texts.append(f"=== {os.path.basename(fp)} ===\n{result}")
                ocr_text = "\n\n".join(ocr_texts)

                st.session_state.inputs = {
                    "intake_source": intake_source, "ocr_text": ocr_text,
                    "erp_system": erp_system, "notification_channel": notification_channel,
                }
                st.rerun()

    elif st.session_state.phase == "extracting":
        # ── Processing animation ──────────────────────────────────────────────
        st.markdown("""
        <div style="text-align:center;padding:60px 20px;">
            <div style="display:inline-block;width:64px;height:64px;border:4px solid #bfdbfe;border-top:4px solid #1a56db;border-radius:50%;animation:spin 1s linear infinite;margin-bottom:24px;"></div>
            <div style="font-size:22px;font-weight:600;color:#1a56db;margin-bottom:8px;">Processing Invoice</div>
            <div style="font-size:14px;color:#6b7280;">AI agents are extracting and validating data...</div>
            <div style="margin-top:24px;display:flex;justify-content:center;gap:8px;">
                <span style="width:8px;height:8px;background:#1a56db;border-radius:50%;display:inline-block;animation:pulse 1.4s ease-in-out 0s infinite;"></span>
                <span style="width:8px;height:8px;background:#1a56db;border-radius:50%;display:inline-block;animation:pulse 1.4s ease-in-out 0.2s infinite;"></span>
                <span style="width:8px;height:8px;background:#1a56db;border-radius:50%;display:inline-block;animation:pulse 1.4s ease-in-out 0.4s infinite;"></span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        step_outputs = []
        result_holder = {"result": None, "error": None, "logs": ""}

        def task_callback(task_output):
            step_outputs.append({
                "name": getattr(task_output, "name", "Unknown"),
                "agent": getattr(task_output, "agent", ""),
                "raw": getattr(task_output, "raw", str(task_output)),
            })

        t = threading.Thread(target=run_extraction_crew,
                             args=(st.session_state.inputs, step_outputs, result_holder, task_callback))
        t.start(); t.join()

        st.session_state.step_outputs = step_outputs
        st.session_state.run_error = result_holder.get("error")
        st.session_state.logs = result_holder.get("logs", "")

        extracted_json = None
        for step in step_outputs:
            if step["name"] == "structured_data_extraction":
                parsed = parse_json(step["raw"])
                if parsed: parsed = verify_and_fix_totals(parsed)
                extracted_json = parsed
                if not parsed:
                    # Store raw for debug
                    st.session_state["extraction_raw_debug"] = step["raw"][:500]

        st.session_state.extracted_json = extracted_json

        if not result_holder.get("error") and extracted_json:
            sheet_id = os.environ.get("GOOGLE_SHEET_ID")
            if sheet_id:
                save_invoice(extracted_json, st.session_state.file_name, "PENDING", user_email="streamlit_user")

        st.session_state.phase = "done"
        st.rerun()

    elif st.session_state.phase == "done":
        if st.session_state.run_error:
            st.error(f"Processing failed: {st.session_state.run_error}")
            with st.expander("Technical Details"):
                st.code(st.session_state.logs, language="text")
        elif st.session_state.extracted_json:
            st.success("✅ Invoice processed successfully — review below and approve/reject in the Processed Invoices tab.")
            render_invoice(st.session_state.extracted_json)
            with st.expander("🔧 Technical Details", expanded=False):
                for step in st.session_state.step_outputs:
                    st.markdown(f"**{step['name']}**")
                    st.markdown(step["raw"])
                    st.divider()
        else:
            st.warning("Processing completed but no structured data was extracted.")
            if st.session_state.get("extraction_raw_debug"):
                with st.expander("Debug — raw extraction output"):
                    st.code(st.session_state["extraction_raw_debug"], language="text")
            with st.expander("Technical Details"):
                st.code(st.session_state.logs, language="text")

        if st.button("Process Another Invoice"):
            st.session_state.phase = "idle"
            st.session_state.extracted_json = None
            st.session_state.step_outputs = []
            st.rerun()

# ── TAB 2 ─────────────────────────────────────────────────────────────────────
with tab_history:
    st.markdown('<h3 style="color:#4a9eff;">Processed Invoices</h3>', unsafe_allow_html=True)

    if not os.environ.get("GOOGLE_SHEET_ID"):
        st.info("Google Sheets not configured. Set GOOGLE_SHEET_ID in .env to enable history.")
    else:
        if st.button("🔄 Refresh"):
            st.rerun()

        records = get_processed_invoices()
        if not records:
            st.info("No processed invoices yet.")
        else:
            import pandas as pd
            df = pd.DataFrame(records).astype(str).replace("nan","").replace("None","")

            # Metrics
            total = len(df)
            pending = len(df[df.get("Approval Status","") == "PENDING"]) if "Approval Status" in df.columns else 0
            approved = len(df[df["Approval Status"].str.startswith("APPROVED")]) if "Approval Status" in df.columns else 0
            rejected = len(df[df["Approval Status"].str.startswith("REJECTED")]) if "Approval Status" in df.columns else 0
            m1,m2,m3,m4 = st.columns(4)
            m1.metric("Total",total); m2.metric("Pending",pending)
            m3.metric("Approved",approved); m4.metric("Rejected",rejected)

            st.divider()

            # Summary table — only the fields user requested
            show = ["Timestamp","Invoice Number","Invoice Date","Due Date",
                    "Receiver Name","Subtotal","Tax Amount","Total Amount","Currency","Approval Status"]
            show_cols = [c for c in show if c in df.columns]
            st.dataframe(df[show_cols], use_container_width=True, hide_index=True)

            st.divider()
            st.markdown('<h4 style="color:#4a9eff;">Approve / Reject</h4>', unsafe_allow_html=True)

            pending_df = df[df["Approval Status"] == "PENDING"] if "Approval Status" in df.columns else df
            if pending_df.empty:
                st.info("No pending invoices.")
            else:
                options = []
                for _, row in pending_df.iterrows():
                    inv_no = row.get("Invoice Number","—")
                    receiver = row.get("Receiver Name","—")
                    total_amt = row.get("Total Amount","—")
                    ts = row.get("Timestamp","")
                    options.append(f"{ts} | #{inv_no} | {receiver} | {total_amt}")

                selected = st.selectbox("Select invoice to review", options)
                idx = options.index(selected)
                row = pending_df.iloc[idx]

                # Show invoice template
                full_json_str = row.get("Full JSON","")
                if full_json_str:
                    try:
                        inv_data = json.loads(full_json_str)
                        render_invoice(inv_data)
                    except Exception:
                        # Fallback summary
                        sc1,sc2,sc3,sc4,sc5 = st.columns(5)
                        sc1.metric("Invoice #", row.get("Invoice Number","—"))
                        sc2.metric("Date", row.get("Invoice Date","—"))
                        sc3.metric("Due", row.get("Due Date","—"))
                        sc4.metric("Bill To", row.get("Receiver Name","—"))
                        sc5.metric("Total", f"{row.get('Total Amount','—')} {row.get('Currency','')}")

                row_number = pending_df.index[idx] + 2
                btn1, btn2 = st.columns(2)
                with btn1:
                    if st.button("✅ Approve", use_container_width=True, type="primary"):
                        ok, err = update_approval_status(row_number, "APPROVED")
                        if ok: st.success("Approved."); st.rerun()
                        else: st.error(f"Failed: {err}")
                with btn2:
                    reject_reason = st.text_input("Rejection reason (optional)", key="reject_reason")
                    if st.button("❌ Reject", use_container_width=True):
                        ok, err = update_approval_status(row_number, f"REJECTED: {reject_reason}")
                        if ok: st.warning("Rejected."); st.rerun()
                        else: st.error(f"Failed: {err}")

st.divider()
st.markdown('<p style="text-align:center;color:#9ca3af;font-size:12px;">Invoice Processing Automation System • CrewAI</p>', unsafe_allow_html=True)
