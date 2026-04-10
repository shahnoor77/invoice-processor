import os
import threading
from typing import Callable, Optional
from dataclasses import dataclass

import litellm
from crewai import LLM, Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from invoice_processing_automation_system.tools.custom_tool import PDFTextExtractor, ImageTextExtractor, GmailInvoiceFetcher

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://110.39.187.178:11434")
OLLAMA_MODEL = "ollama/qwen3.5:9b"

os.environ.setdefault("OLLAMA_API_BASE", OLLAMA_BASE_URL)
litellm.add_function_to_prompt = True

# Thread-local storage for user config.
# This ensures each worker thread uses its own user's config,
# even if CrewAI creates agents early in the lifecycle.
_thread_local = threading.local()


@dataclass
class UserLLMConfig:
    """Per-user LLM configuration from database."""
    user_id: Optional[str] = None  # Include user_id for cache isolation
    model_name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


# Cache LLM instances per user config to avoid recreating for each agent
# Structure: {user_id: {cache_key: LLM}} - user-scoped for security
_llm_cache: dict[str, dict[str, LLM]] = {}


def _make_cache_key(model: str, api_key: Optional[str], base_url: Optional[str], temperature: float) -> str:
    """Create a cache key from LLM parameters."""
    return f"{model}:{api_key or ''}:{base_url or ''}:{temperature}"


def make_llm(
    temperature: float = 0.1,
    user_config: Optional[UserLLMConfig] = None
) -> LLM:
    """
    Create an LLM instance with optional per-user configuration.
    Checks: 1. Explicit arg -> 2. Thread-local -> 3. Env vars
    """
    # If no explicit config is provided, check the thread-local storage first
    if user_config is None:
        user_config = getattr(_thread_local, 'user_config', None)

    # Initialize with system defaults
    model = os.environ.get("MODEL", OLLAMA_MODEL)
    api_key = os.environ.get("MODEL_API_KEY")
    ollama_base_url = os.environ.get("OLLAMA_BASE_URL", OLLAMA_BASE_URL)
    user_id = None
    
    # Override with user-specific config if provided
    if user_config:
        model = user_config.model_name or model
        api_key = user_config.api_key or api_key
        # ollama_base_url = user_config.base_url or ollama_base_url
        user_id = user_config.user_id

    is_ollama = model.startswith("ollama/")
    if is_ollama:
        os.environ["OLLAMA_API_BASE"] = ollama_base_url
    print("Model name: ", model, "API Key set: ", api_key)
    # Check cache with user-scoped isolation
    cache_key = _make_cache_key(model, api_key, ollama_base_url, temperature)
    if user_id and user_id in _llm_cache and cache_key in _llm_cache[user_id]:
        return _llm_cache[user_id][cache_key]
    # For system-wide config (no user_id), check global cache
    if not user_id and "system" in _llm_cache and cache_key in _llm_cache["system"]:
        return _llm_cache["system"][cache_key]
    
    # extra_kwargs = {}
    # if "qwen3" in model.lower():
    #     extra_kwargs["extra_body"] = {"think": False}
    
    llm_instance = LLM(
        model=model,
        base_url=ollama_base_url if is_ollama else None,
        api_key=api_key if not is_ollama else None,
        temperature=temperature,
        timeout=300,
        max_retries=3,
        max_tokens=4096,
        # **extra_kwargs,
    )
    
    # Cache the instance in user-specific namespace
    if user_id:
        if user_id not in _llm_cache:
            _llm_cache[user_id] = {}
        _llm_cache[user_id][cache_key] = llm_instance
    else:
        if "system" not in _llm_cache:
            _llm_cache["system"] = {}
        _llm_cache["system"][cache_key] = llm_instance
    
    return llm_instance


@CrewBase
class InvoiceProcessingAutomationSystemCrew:
    """InvoiceProcessingAutomationSystem crew"""

    _task_callback: Optional[Callable] = None
    _user_config: Optional[UserLLMConfig] = None

    def set_task_callback(self, callback: Callable):
        self._task_callback = callback
        return self
    
    def set_user_config(self, user_config: UserLLMConfig):
        """Set per-user LLM configuration from database."""
        self._user_config = user_config
        return self
    
    @agent
    def document_intake_specialist(self) -> Agent:
        return Agent(
            config=self.agents_config["document_intake_specialist"],
            tools=[PDFTextExtractor(), ImageTextExtractor()],
            reasoning=False,
            inject_date=False,
            allow_delegation=False,
            max_iter=3,
            llm=make_llm(user_config=self._user_config),
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
            llm=make_llm(temperature=0, user_config=self._user_config),  # zero temp for deterministic extraction
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
            llm=make_llm(user_config=self._user_config),
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
            apps=["google_sheets/append_values"],
            llm=make_llm(user_config=self._user_config),
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
            apps=["google_gmail/send_email"],
            llm=make_llm(user_config=self._user_config),
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
        llm = make_llm(user_config=self._user_config)
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
            llm=llm,
            chat_llm=llm,
            task_callback=self._task_callback,
        )
