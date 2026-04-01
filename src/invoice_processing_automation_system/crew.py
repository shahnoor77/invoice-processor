import os
from typing import Callable, Optional

import litellm
from crewai import LLM, Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from invoice_processing_automation_system.tools.custom_tool import PDFTextExtractor, ImageTextExtractor

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://110.39.187.178:11434")
OLLAMA_MODEL = "ollama/qwen3.5:9b"

os.environ.setdefault("OLLAMA_API_BASE", OLLAMA_BASE_URL)
litellm.add_function_to_prompt = True


def make_llm(temperature: float = 0.1):
    model = os.environ.get("MODEL", OLLAMA_MODEL)
    ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://110.39.187.178:11434")
    is_ollama = model.startswith("ollama/")
    if is_ollama:
        os.environ["OLLAMA_API_BASE"] = ollama_base_url
    extra_kwargs = {}
    if "qwen3" in model.lower():
        extra_kwargs["extra_body"] = {"think": False}
    return LLM(
        model=model,
        base_url=ollama_base_url if is_ollama else None,
        api_key=None if is_ollama else os.environ.get("MODEL_API_KEY"),
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

    def set_task_callback(self, callback: Callable):
        self._task_callback = callback
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
            llm=make_llm(),
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
            llm=make_llm(temperature=0),  # zero temp for deterministic extraction
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
            llm=make_llm(),
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
            llm=make_llm(),
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
            llm=make_llm(),
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
        llm = make_llm()
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
            llm=llm,
            chat_llm=llm,
            task_callback=self._task_callback,
        )
