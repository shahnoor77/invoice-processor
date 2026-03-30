import os
from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field


class PDFTextExtractorInput(BaseModel):
    """Input schema for PDFTextExtractor."""
    file_path: str = Field(..., description="The absolute file path to the PDF file to extract text from.")


class PDFTextExtractor(BaseTool):
    name: str = "pdf_text_extractor"
    description: str = (
        "Extracts all text content from a PDF file given its absolute file path. "
        "Use this tool to read and extract text from PDF invoice files. "
        "Returns the full text content of every page in the PDF."
    )
    args_schema: Type[BaseModel] = PDFTextExtractorInput

    def _run(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            return f"Error: File not found at {file_path}"
        if not file_path.lower().endswith(".pdf"):
            return f"Error: File is not a PDF: {file_path}"
        try:
            import pdfplumber
            text_pages = []
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    page_text = page.extract_text()
                    if page_text:
                        text_pages.append(f"--- Page {i+1} ---\n{page_text}")
                    tables = page.extract_tables()
                    if tables:
                        for t_idx, table in enumerate(tables):
                            table_str = "\n".join(["\t".join([cell or "" for cell in row]) for row in table])
                            text_pages.append(f"--- Page {i+1} Table {t_idx+1} ---\n{table_str}")
            if not text_pages:
                return f"No text could be extracted from {file_path}. The PDF may be image-only — try using OCR."
            return "\n\n".join(text_pages)
        except Exception as e:
            return f"Error extracting text from PDF: {str(e)}"


class ImageTextExtractorInput(BaseModel):
    """Input schema for ImageTextExtractor."""
    file_path: str = Field(..., description="The absolute file path to the image file (PNG, JPG, JPEG).")


class ImageTextExtractor(BaseTool):
    name: str = "image_text_extractor"
    description: str = (
        "Extracts text from an image file (PNG, JPG, JPEG) using OCR. "
        "Use this for image-based invoices that are not PDFs."
    )
    args_schema: Type[BaseModel] = ImageTextExtractorInput

    def _run(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            return f"Error: File not found at {file_path}"
        try:
            import pymupdf
            doc = pymupdf.open(file_path)
            text_parts = []
            for i, page in enumerate(doc):
                text = page.get_text()
                if text.strip():
                    text_parts.append(f"--- Page {i+1} ---\n{text}")
            doc.close()
            if not text_parts:
                return f"No text could be extracted from {file_path}."
            return "\n\n".join(text_parts)
        except Exception as e:
            return f"Error extracting text from image: {str(e)}"
