import logging
import os
from dataclasses import dataclass
from typing import Callable, Optional

import litellm
from crewai import LLM, Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from invoice_processing_automation_system.tools.custom_tool import PDFTextExtractor, ImageTextExtractor, GmailInvoiceFetcher

log = logging.getLogger("crew")

_DEFAULT_MODEL = "ollama/qwen3.5:9b"
_DEFAULT_BASE_URL = "http://110.39.187.178:11434"

litellm.add_function_to_prompt = True

# LLM instance cache — keyed by (model, api_key, base_url, temperature)
# Avoids recreating identical LLM objects for each agent in a crew run
_llm_cache: dict[str, LLM] = {}


def _llm_cache_key(cfg: "ModelConfig", temperature: float) -> str:
    return f"{cfg.model}:{cfg.api_key or ''}:{cfg.base_url or ''}:{temperature}"


@dataclass
class ModelConfig:
    """Resolved model settings for one job — never touches os.environ."""
    model: str
    api_key: Optional[str]
    base_url: Optional[str]

    @staticmethod
    def from_env() -> "ModelConfig":
        """Build from process environment (system default)."""
        return ModelConfig(
            model=os.environ.get("MODEL", _DEFAULT_MODEL),
            api_key=os.environ.get("MODEL_API_KEY") or None,
            base_url=os.environ.get("OLLAMA_BASE_URL", _DEFAULT_BASE_URL),
        )

    def describe(self) -> str:
        """Human-readable summary for logging."""
        is_ollama = self.model.startswith("ollama/")
        if is_ollama:
            return f"{self.model} @ {self.base_url or 'default'}"
        return f"{self.model} (api_key={'set' if self.api_key else 'MISSING'})"


def make_llm(temperature: float = 0.1, cfg: Optional[ModelConfig] = None) -> LLM:
    """
    Build (or return cached) LLM instance from a ModelConfig.
    Falls back to process environment when cfg is None.
    Never mutates os.environ — safe for concurrent threads.
    """
    if cfg is None:
        cfg = ModelConfig.from_env()

    # Return cached instance if same config was used before
    key = _llm_cache_key(cfg, temperature)
    if key in _llm_cache:
        return _llm_cache[key]

    is_ollama = cfg.model.startswith("ollama/")

    extra_kwargs: dict = {}
    if "qwen3" in cfg.model.lower():
        extra_kwargs["extra_body"] = {"think": False}

    log.info(f"[LLM] Building LLM → {cfg.describe()} (temp={temperature})")

    if not is_ollama and not cfg.api_key:
        log.warning(f"[LLM] Cloud model {cfg.model} has no api_key — requests will likely fail")

    llm = LLM(
        model=cfg.model,
        base_url=cfg.base_url if is_ollama else None,
        api_key=cfg.api_key if (not is_ollama and cfg.api_key) else None,
        temperature=temperature,
        timeout=300,
        max_retries=3,
        max_tokens=8192,
        **extra_kwargs,
    )
    _llm_cache[key] = llm
    return llm


@CrewBase
class InvoiceProcessingAutomationSystemCrew:
    """InvoiceProcessingAutomationSystem crew"""

    _task_callback: Optional[Callable] = None
    _model_cfg: Optional[ModelConfig] = None
    _captured_extraction: Optional[dict] = None  # captures full JSON before CrewAI truncates .raw

    def set_task_callback(self, callback: Callable) -> "InvoiceProcessingAutomationSystemCrew":
        self._task_callback = callback
        return self

    def set_model_config(self, cfg: ModelConfig) -> "InvoiceProcessingAutomationSystemCrew":
        self._model_cfg = cfg
        log.info(f"[Crew] Model config set → {cfg.describe()}")
        return self

    def _llm(self, temperature: float = 0.1) -> LLM:
        return make_llm(temperature=temperature, cfg=self._model_cfg)

    def _step_callback(self, step_output) -> None:
        """Capture the extraction agent's full JSON output before CrewAI truncates .raw."""
        try:
            # step_output can be AgentFinish, AgentAction, or a string
            text = None
            if hasattr(step_output, 'output'):
                text = str(step_output.output)
            elif hasattr(step_output, 'return_values'):
                text = str(step_output.return_values.get('output', ''))
            elif isinstance(step_output, str):
                text = step_output

            if text:
                # Try to find invoice JSON in the output
                import json as _json, re as _re
                # Look for JSON object
                start = text.find('{')
                if start != -1:
                    fragment = text[start:]
                    try:
                        parsed = _json.loads(fragment)
                    except Exception:
                        # Try regex extraction
                        m = _re.search(r'(\{[\s\S]*\})', fragment, _re.DOTALL)
                        parsed = None
                        if m:
                            try:
                                parsed = _json.loads(m.group(1))
                            except Exception:
                                pass
                    if parsed and isinstance(parsed, dict):
                        real_keys = {"invoice_number", "sender", "receiver", "line_items"}
                        if real_keys.intersection(parsed.keys()):
                            self._captured_extraction = parsed
                            log.info(f"[Crew] Step callback captured invoice JSON — keys: {list(parsed.keys())[:6]}")
        except Exception as e:
            log.debug(f"[Crew] Step callback error (non-fatal): {e}")

    @agent
    def document_intake_specialist(self) -> Agent:
        return Agent(
            config=self.agents_config["document_intake_specialist"],
            tools=[PDFTextExtractor(), ImageTextExtractor()],
            reasoning=False,
            inject_date=False,
            allow_delegation=False,
            max_iter=3,
            llm=self._llm(),
        )

    @agent
    def data_extraction_specialist(self) -> Agent:
        return Agent(
            config=self.agents_config["data_extraction_specialist"],
            tools=[],
            reasoning=False,
            inject_date=False,
            allow_delegation=False,
            max_iter=2,
            llm=self._llm(temperature=0),
        )

    @agent
    def data_validation_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["data_validation_analyst"],
            tools=[],
            reasoning=False,
            inject_date=False,
            allow_delegation=False,
            max_iter=2,
            llm=self._llm(),
        )

    @agent
    def erp_integration_specialist(self) -> Agent:
        return Agent(
            config=self.agents_config["erp_integration_specialist"],
            tools=[],
            reasoning=False,
            inject_date=False,
            allow_delegation=False,
            max_iter=2,
            llm=self._llm(),
        )

    @agent
    def finance_notification_coordinator(self) -> Agent:
        return Agent(
            config=self.agents_config["finance_notification_coordinator"],
            tools=[],
            reasoning=False,
            inject_date=False,
            allow_delegation=False,
            max_iter=2,
            llm=self._llm(),
        )

    @task
    def invoice_file_detection_and_intake(self) -> Task:
        return Task(config=self.tasks_config["invoice_file_detection_and_intake"], markdown=False)

    @task
    def structured_data_extraction(self) -> Task:
        return Task(config=self.tasks_config["structured_data_extraction"], markdown=False)

    @task
    def invoice_data_validation(self) -> Task:
        return Task(config=self.tasks_config["invoice_data_validation"], markdown=False)

    @task
    def erp_system_integration(self) -> Task:
        return Task(config=self.tasks_config["erp_system_integration"], markdown=False)

    @task
    def finance_team_notification(self) -> Task:
        return Task(config=self.tasks_config["finance_team_notification"], markdown=False)

    @crew
    def crew(self) -> Crew:
        llm = self._llm()
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
            llm=llm,
            chat_llm=llm,
            task_callback=self._task_callback,
        )

    def crew_minimal(self, erp_system: str = "pending_approval", notification_channel: str = "none") -> Crew:
        """Minimal crew — only extraction + validation. Intake agent removed (OCR done before crew)."""
        llm = self._llm()

        core_agents = [
            self.data_extraction_specialist(),
            self.data_validation_analyst(),
        ]
        core_tasks = [
            self.structured_data_extraction(),
            self.invoice_data_validation(),
        ]

        erp_needed = erp_system and erp_system.lower() not in ("", "none", "pending_approval", "skip")
        if erp_needed:
            log.info(f"[Crew] ERP integration enabled: {erp_system}")
            core_agents.append(self.erp_integration_specialist())
            core_tasks.append(self.erp_system_integration())

        notify_needed = notification_channel and notification_channel.lower() not in ("", "none", "skip")
        if notify_needed:
            log.info(f"[Crew] Notification enabled: {notification_channel}")
            core_agents.append(self.finance_notification_coordinator())
            core_tasks.append(self.finance_team_notification())

        log.info(f"[Crew] Starting minimal crew: {len(core_tasks)} tasks, model={self._model_cfg.describe() if self._model_cfg else 'env-default'}")

        return Crew(
            agents=core_agents,
            tasks=core_tasks,
            process=Process.sequential,
            verbose=True,
            llm=llm,
            chat_llm=llm,
            task_callback=self._task_callback,
            step_callback=self._step_callback,
        )
