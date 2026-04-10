import os
from dataclasses import dataclass
from typing import Callable, Optional

import litellm
from crewai import LLM, Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from invoice_processing_automation_system.tools.custom_tool import PDFTextExtractor, ImageTextExtractor, GmailInvoiceFetcher

_DEFAULT_MODEL = "ollama/qwen3.5:9b"
_DEFAULT_BASE_URL = "http://110.39.187.178:11434"

litellm.add_function_to_prompt = True


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
            api_key=os.environ.get("MODEL_API_KEY"),
            base_url=os.environ.get("OLLAMA_BASE_URL", _DEFAULT_BASE_URL),
        )


def make_llm(temperature: float = 0.1, cfg: Optional[ModelConfig] = None) -> LLM:
    """
    Build an LLM instance from an explicit ModelConfig.
    Falls back to process environment when cfg is None (system default path).
    Never mutates os.environ — safe to call from concurrent threads.
    """
    if cfg is None:
        cfg = ModelConfig.from_env()

    is_ollama = cfg.model.startswith("ollama/")

    extra_kwargs: dict = {}
    if "qwen3" in cfg.model.lower():
        extra_kwargs["extra_body"] = {"think": False}

    return LLM(
        model=cfg.model,
        # base_url only makes sense for ollama; cloud providers use their own endpoints
        base_url=cfg.base_url if is_ollama else None,
        # ollama doesn't need an api_key; cloud providers do
        api_key=cfg.api_key if (not is_ollama and cfg.api_key) else None,
        temperature=temperature,
        timeout=300,
        max_retries=3,
        max_tokens=4096,
        **extra_kwargs,
    )


@CrewBase
class InvoiceProcessingAutomationSystemCrew:
    """InvoiceProcessingAutomationSystem crew"""

    _task_callback: Optional[Callable] = None
    _model_cfg: Optional[ModelConfig] = None

    def set_task_callback(self, callback: Callable) -> "InvoiceProcessingAutomationSystemCrew":
        self._task_callback = callback
        return self

    def set_model_config(self, cfg: ModelConfig) -> "InvoiceProcessingAutomationSystemCrew":
        """Inject per-user model config — call before crew_minimal()."""
        self._model_cfg = cfg
        return self

    def _llm(self, temperature: float = 0.1) -> LLM:
        """Return an LLM built from the injected config (or env default)."""
        return make_llm(temperature=temperature, cfg=self._model_cfg)

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
            llm=self._llm(temperature=0),  # zero temp for deterministic extraction
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
        """
        Returns a crew with only the tasks that are actually needed.
        ERP integration and notification tasks are skipped when not configured.
        Uses the injected ModelConfig — no os.environ mutation.
        """
        llm = self._llm()

        core_agents = [
            self.document_intake_specialist(),
            self.data_extraction_specialist(),
            self.data_validation_analyst(),
        ]
        core_tasks = [
            self.invoice_file_detection_and_intake(),
            self.structured_data_extraction(),
            self.invoice_data_validation(),
        ]

        erp_needed = erp_system and erp_system.lower() not in ("", "none", "pending_approval", "skip")
        if erp_needed:
            core_agents.append(self.erp_integration_specialist())
            core_tasks.append(self.erp_system_integration())

        notify_needed = notification_channel and notification_channel.lower() not in ("", "none", "skip")
        if notify_needed:
            core_agents.append(self.finance_notification_coordinator())
            core_tasks.append(self.finance_team_notification())

        return Crew(
            agents=core_agents,
            tasks=core_tasks,
            process=Process.sequential,
            verbose=True,
            llm=llm,
            chat_llm=llm,
            task_callback=self._task_callback,
        )
