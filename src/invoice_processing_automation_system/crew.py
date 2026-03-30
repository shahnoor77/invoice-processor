import os
from typing import Callable, Optional

from crewai import LLM
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import (
	FileReadTool,
	OCRTool
)
from invoice_processing_automation_system.tools.custom_tool import PDFTextExtractor, ImageTextExtractor





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
            
            
            tools=[FileReadTool(), PDFTextExtractor(), ImageTextExtractor()],
            reasoning=False,
            max_reasoning_attempts=None,
            inject_date=True,
            allow_delegation=False,
            max_iter=25,
            max_rpm=None,
            
            
            max_execution_time=None,
            llm=LLM(
                model="openai/gpt-4o-mini",
                temperature=0.7,
                
            ),
            
        )
    
    @agent
    def ocr_processing_specialist(self) -> Agent:
        
        return Agent(
            config=self.agents_config["ocr_processing_specialist"],
            
            
            tools=[OCRTool(), PDFTextExtractor(), ImageTextExtractor()],
            reasoning=False,
            max_reasoning_attempts=None,
            inject_date=True,
            allow_delegation=False,
            max_iter=25,
            max_rpm=None,
            
            
            max_execution_time=None,
            llm=LLM(
                model="openai/gpt-4o-mini",
                temperature=0.7,
                
            ),
            
        )
    
    @agent
    def layout_analysis_expert(self) -> Agent:
        
        return Agent(
            config=self.agents_config["layout_analysis_expert"],
            
            
            tools=[],
            reasoning=False,
            max_reasoning_attempts=None,
            inject_date=True,
            allow_delegation=False,
            max_iter=25,
            max_rpm=None,
            
            
            max_execution_time=None,
            llm=LLM(
                model="openai/gpt-4o-mini",
                temperature=0.7,
                
            ),
            
        )
    
    @agent
    def data_extraction_specialist(self) -> Agent:
        
        return Agent(
            config=self.agents_config["data_extraction_specialist"],
            
            
            tools=[],
            reasoning=False,
            max_reasoning_attempts=None,
            inject_date=True,
            allow_delegation=False,
            max_iter=25,
            max_rpm=None,
            
            
            max_execution_time=None,
            llm=LLM(
                model="openai/gpt-4o-mini",
                temperature=0.7,
                
            ),
            
        )
    
    @agent
    def data_validation_analyst(self) -> Agent:
        
        return Agent(
            config=self.agents_config["data_validation_analyst"],
            
            
            tools=[],
            reasoning=False,
            max_reasoning_attempts=None,
            inject_date=True,
            allow_delegation=False,
            max_iter=25,
            max_rpm=None,
            
            
            max_execution_time=None,
            llm=LLM(
                model="openai/gpt-4o-mini",
                temperature=0.7,
                
            ),
            
        )
    
    @agent
    def erp_integration_specialist(self) -> Agent:
        
        return Agent(
            config=self.agents_config["erp_integration_specialist"],
            
            
            tools=[],
            reasoning=False,
            max_reasoning_attempts=None,
            inject_date=True,
            allow_delegation=False,
            max_iter=25,
            max_rpm=None,
            
            apps=[
                    "google_sheets/append_values",
                    ],
            
            
            max_execution_time=None,
            llm=LLM(
                model="openai/gpt-4o-mini",
                temperature=0.7,
                
            ),
            
        )
    
    @agent
    def finance_notification_coordinator(self) -> Agent:
        
        return Agent(
            config=self.agents_config["finance_notification_coordinator"],
            
            
            tools=[],
            reasoning=False,
            max_reasoning_attempts=None,
            inject_date=True,
            allow_delegation=False,
            max_iter=25,
            max_rpm=None,
            
            apps=[
                    "google_gmail/send_email",
                    ],
            
            
            max_execution_time=None,
            llm=LLM(
                model="openai/gpt-4o-mini",
                temperature=0.7,
                
            ),
            
        )
    

    
    @task
    def invoice_file_detection_and_intake(self) -> Task:
        return Task(
            config=self.tasks_config["invoice_file_detection_and_intake"],
            markdown=False,
            
            
        )
    
    @task
    def ocr_text_extraction(self) -> Task:
        return Task(
            config=self.tasks_config["ocr_text_extraction"],
            markdown=False,
            
            
        )
    
    @task
    def invoice_layout_analysis(self) -> Task:
        return Task(
            config=self.tasks_config["invoice_layout_analysis"],
            markdown=False,
            
            
        )
    
    @task
    def structured_data_extraction(self) -> Task:
        return Task(
            config=self.tasks_config["structured_data_extraction"],
            markdown=False,
            
            
        )
    
    @task
    def invoice_data_validation(self) -> Task:
        return Task(
            config=self.tasks_config["invoice_data_validation"],
            markdown=False,
            
            
        )
    
    @task
    def erp_system_integration(self) -> Task:
        return Task(
            config=self.tasks_config["erp_system_integration"],
            markdown=False,
            
            
        )
    
    @task
    def finance_team_notification(self) -> Task:
        return Task(
            config=self.tasks_config["finance_team_notification"],
            markdown=False,
            
            
        )
    

    @crew
    def crew(self) -> Crew:
        """Creates the InvoiceProcessingAutomationSystem crew"""
        return Crew(
            agents=self.agents,  # Automatically created by the @agent decorator
            tasks=self.tasks,  # Automatically created by the @task decorator
            process=Process.sequential,
            verbose=True,
            chat_llm=LLM(model="openai/gpt-4o-mini"),
            task_callback=self._task_callback,
        )


