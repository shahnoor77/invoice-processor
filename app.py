#!/usr/bin/env python
import streamlit as st
import threading
import sys
import io
import os
import tempfile
from dotenv import load_dotenv

load_dotenv()

# Support Streamlit Cloud secrets
if "OPENAI_API_KEY" in st.secrets:
    os.environ["OPENAI_API_KEY"] = st.secrets["OPENAI_API_KEY"]

from invoice_processing_automation_system.crew import InvoiceProcessingAutomationSystemCrew


st.set_page_config(
    page_title="Invoice Processing Automation",
    page_icon="🧾",
    layout="wide",
)

st.title("🧾 Invoice Processing Automation System")
st.markdown("Powered by **CrewAI** — upload invoice files and let the agents process them end-to-end.")

st.divider()

uploaded_files = st.file_uploader(
    "📂 Upload Invoice Files",
    type=["pdf", "png", "jpg", "jpeg"],
    accept_multiple_files=True,
    help="Upload one or more invoice files (PDF, PNG, JPG).",
)

with st.form("crew_inputs"):
    col1, col2 = st.columns(2)

    with col1:
        erp_system = st.text_input(
            "🏢 ERP System",
            placeholder="e.g. SAP, QuickBooks, NetSuite",
            help="The target ERP/accounting system to push validated data to.",
        )

    with col2:
        notification_channel = st.text_input(
            "🔔 Notification Channel",
            placeholder="e.g. email, Slack #finance-team",
            help="Channel to notify the finance team about processing results.",
        )

    extra_prompt = st.text_area(
        "💬 Additional Instructions (optional)",
        placeholder="Any extra instructions or context for the agents...",
        height=100,
        help="Additional prompt/instructions to guide the crew's behavior.",
    )

    submitted = st.form_submit_button("🚀 Run Invoice Processing Crew", use_container_width=True)

if submitted:
    if not uploaded_files or not erp_system or not notification_channel:
        st.error("Please upload at least one invoice file and fill in all required fields.")
    else:
        # Save uploaded files to a temp directory
        upload_dir = tempfile.mkdtemp(prefix="invoices_")
        saved_paths = []
        for uf in uploaded_files:
            file_path = os.path.join(upload_dir, uf.name)
            with open(file_path, "wb") as f:
                f.write(uf.getbuffer())
            saved_paths.append(file_path)

        st.info(f"📁 {len(saved_paths)} file(s) saved: {', '.join(os.path.basename(p) for p in saved_paths)}")

        # Pass full file paths so agents can directly read them
        file_list = "\n".join(saved_paths)
        intake_source = f"Directory: {upload_dir}\n\nFiles to process:\n{file_list}"
        if extra_prompt:
            intake_source += f"\n\nAdditional instructions: {extra_prompt}"

        inputs = {
            "intake_source": intake_source,
            "erp_system": erp_system,
            "notification_channel": notification_channel,
        }

        st.divider()
        st.subheader("⚙️ Crew Execution")

        log_container = st.empty()
        status_placeholder = st.empty()

        status_placeholder.info("🔄 Running the crew... This may take a few minutes.")

        class StreamCapture(io.StringIO):
            """Captures stdout and stores it for display."""
            def __init__(self):
                super().__init__()
                self._log = []
                self._original_stdout = sys.stdout

            def write(self, text):
                self._original_stdout.write(text)
                if text.strip():
                    self._log.append(text)
                return len(text)

            def flush(self):
                self._original_stdout.flush()

            def get_log(self):
                return "\n".join(self._log)

        capture = StreamCapture()
        result_holder = {"result": None, "error": None}
        step_outputs = []

        TASK_LABELS = {
            "invoice_file_detection_and_intake": ("1️⃣", "Document Intake", "File detection, format validation, and intake logging"),
            "ocr_text_extraction": ("2️⃣", "OCR Text Extraction", "Text extraction from invoice using OCR"),
            "invoice_layout_analysis": ("3️⃣", "Layout Analysis", "Invoice structure and section identification"),
            "structured_data_extraction": ("4️⃣", "Data Extraction", "Structured data (JSON) extraction from invoice"),
            "invoice_data_validation": ("5️⃣", "Data Validation", "Mathematical and logical validation of extracted data"),
            "erp_system_integration": ("6️⃣", "ERP Integration", "Push validated data to ERP system"),
            "finance_team_notification": ("7️⃣", "Finance Notification", "Notify finance team of processing results"),
        }

        def task_callback(task_output):
            name = task_output.name if hasattr(task_output, "name") else "Unknown"
            agent_name = task_output.agent if hasattr(task_output, "agent") else ""
            raw = task_output.raw if hasattr(task_output, "raw") else str(task_output)
            step_outputs.append({"name": name, "agent": agent_name, "raw": raw})

        def run_crew():
            old_stdout = sys.stdout
            sys.stdout = capture
            try:
                crew_instance = InvoiceProcessingAutomationSystemCrew()
                crew_instance.set_task_callback(task_callback)
                result = crew_instance.crew().kickoff(inputs=inputs)
                result_holder["result"] = result
            except Exception as e:
                result_holder["error"] = str(e)
            finally:
                sys.stdout = old_stdout

        thread = threading.Thread(target=run_crew)
        thread.start()
        thread.join()

        if result_holder["error"]:
            status_placeholder.error(f"❌ Crew execution failed: {result_holder['error']}")
        else:
            status_placeholder.success("✅ Crew execution completed successfully!")

        # Show logs
        logs = capture.get_log()
        if logs:
            with st.expander("📋 Raw Execution Logs", expanded=False):
                st.code(logs, language="text")

        # Show step-by-step agent outputs
        if step_outputs:
            st.divider()
            st.subheader("📊 Step-by-Step Agent Outputs")
            for i, step in enumerate(step_outputs):
                name = step["name"]
                label_info = TASK_LABELS.get(name, (f"🔹", name, ""))
                icon, title, desc = label_info
                agent_str = f" — Agent: **{step['agent']}**" if step["agent"] else ""
                header = f"{icon} Step {i+1}: {title}{agent_str}"
                if desc:
                    header += f"\n> {desc}"
                with st.expander(f"{icon} Step {i+1}: {title}", expanded=True):
                    if desc:
                        st.caption(desc)
                    if step["agent"]:
                        st.markdown(f"**Agent:** {step['agent']}")
                    st.markdown("---")
                    st.markdown(step["raw"])

        # Show final results
        if result_holder["result"] is not None:
            result = result_holder["result"]
            st.divider()
            st.subheader("📄 Final Output")
            raw = result.raw if hasattr(result, "raw") else str(result)
            st.markdown(raw)

            # Token usage
            if hasattr(result, "token_usage") and result.token_usage:
                with st.expander("📈 Token Usage"):
                    st.json(
                        result.token_usage
                        if isinstance(result.token_usage, dict)
                        else str(result.token_usage)
                    )

st.divider()
st.caption("Invoice Processing Automation System • CrewAI")
