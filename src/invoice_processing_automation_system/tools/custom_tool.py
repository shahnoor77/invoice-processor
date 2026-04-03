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

            if text_pages:
                return "PDF_RESULT: TEXT-BASED PDF, HIGH CONFIDENCE.\n\n" + "\n\n".join(text_pages)

            # pdfplumber returned nothing — PDF is image-based, fall back to OCR
            return self._ocr_pdf(file_path)

        except Exception as e:
            return f"Error extracting text from PDF: {str(e)}"

    def _ocr_pdf(self, file_path: str) -> str:
        """OCR fallback for image-based/scanned PDFs."""
        try:
            import pymupdf
            import pytesseract
            from PIL import Image, ImageFilter, ImageEnhance
            import io

            tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if os.path.exists(tesseract_path):
                pytesseract.pytesseract.tesseract_cmd = tesseract_path

            doc = pymupdf.open(file_path)
            all_text = []
            all_confidences = []

            for i, page in enumerate(doc):
                # Render page to image at 300 DPI
                mat = pymupdf.Matrix(300 / 72, 300 / 72)
                pix = page.get_pixmap(matrix=mat, colorspace=pymupdf.csGRAY)
                img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")

                # Preprocess
                img = img.filter(ImageFilter.MedianFilter(size=3))
                img = img.filter(ImageFilter.SHARPEN)
                img = img.filter(ImageFilter.SHARPEN)
                img = img.filter(ImageFilter.SHARPEN)
                img = ImageEnhance.Contrast(img).enhance(3.0)
                import numpy as np
                arr = np.array(img)
                threshold = int((arr.min() + arr.max()) / 2)
                img = img.point(lambda p: 255 if p > threshold else 0)

                data = pytesseract.image_to_data(img, config="--psm 6 --oem 3", output_type=pytesseract.Output.DICT)
                confs = [int(c) for c in data["conf"] if int(c) > 0]
                all_confidences.extend(confs)

                text = pytesseract.image_to_string(img, config="--psm 6 --oem 3")
                if text.strip():
                    all_text.append(f"--- Page {i+1} ---\n{text}")

            doc.close()

            if not all_text:
                return "PDF_RESULT: No text could be extracted. PDF may be corrupted or unreadable. Do NOT fabricate — mark all fields as null."

            avg_conf = sum(all_confidences) / len(all_confidences) if all_confidences else 0
            combined = "\n\n".join(all_text)

            if avg_conf < 50:
                return (
                    f"PDF_RESULT: SCANNED PDF, LOW CONFIDENCE ({avg_conf:.0f}%). Text may be inaccurate.\n"
                    f"IMPORTANT: Mark uncertain or missing fields as null. Do NOT guess.\n\n{combined}"
                )
            return f"PDF_RESULT: SCANNED PDF, HIGH CONFIDENCE ({avg_conf:.0f}%).\n\n{combined}"

        except Exception as e:
            return f"Error during OCR fallback for PDF: {str(e)}"


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
            import pytesseract
            from PIL import Image, ImageFilter, ImageEnhance
            import numpy as np

            # Set tesseract path for Windows if needed
            tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if os.path.exists(tesseract_path):
                pytesseract.pytesseract.tesseract_cmd = tesseract_path
            # On Linux, tesseract is in PATH by default (installed via apt)

            img = Image.open(file_path)
            # Handle palette images with transparency
            if img.mode in ("P", "PA"):
                img = img.convert("RGBA")
            img = img.convert("L")  # grayscale

            # Upscale small images — Tesseract works best at 300 DPI equivalent
            w, h = img.size
            if w < 1500 or h < 1500:
                scale = max(1500 / w, 1500 / h)
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

            # Denoise + sharpen + contrast
            img = img.filter(ImageFilter.MedianFilter(size=3))  # remove noise
            img = img.filter(ImageFilter.SHARPEN)
            img = img.filter(ImageFilter.SHARPEN)
            img = img.filter(ImageFilter.SHARPEN)
            img = ImageEnhance.Contrast(img).enhance(3.0)  # stronger contrast

            # Adaptive binarization — better than fixed threshold for mixed lighting
            import numpy as np
            arr = np.array(img)
            # Use Otsu-like threshold: mean of min and max
            threshold = int((arr.min() + arr.max()) / 2)
            img = img.point(lambda p: 255 if p > threshold else 0)

            # Get OCR with confidence data
            data = pytesseract.image_to_data(img, config="--psm 6 --oem 3", output_type=pytesseract.Output.DICT)

            words = [w for w, c in zip(data["text"], data["conf"]) if w.strip() and int(c) > 0]
            confidences = [int(c) for c in data["conf"] if int(c) > 0]

            if not words:
                return "OCR_RESULT: No text could be extracted. Image may be too blurry or low quality. Do NOT fabricate any data — mark all fields as null."

            avg_conf = sum(confidences) / len(confidences) if confidences else 0
            text = pytesseract.image_to_string(img, config="--psm 6 --oem 3")

            if avg_conf < 50:
                return (
                    f"OCR_RESULT: LOW CONFIDENCE ({avg_conf:.0f}%). Text may be inaccurate due to poor image quality.\n"
                    f"IMPORTANT: Only use values you are certain about. Mark uncertain or missing fields as null. Do NOT guess or fabricate.\n\n"
                    f"Extracted text:\n{text}"
                )

            return f"OCR_RESULT: HIGH CONFIDENCE ({avg_conf:.0f}%).\n\nExtracted text:\n{text}"

        except Exception as e:
            return f"Error extracting text from image: {str(e)}"


def extract_image_with_llava(file_path: str, ollama_base_url: str = "http://110.39.187.178:11434") -> str:
    """
    Send image directly to LLaVA vision model for invoice data extraction.
    Returns raw text description of the invoice content.
    No OCR needed — LLaVA reads the image natively.
    """
    import base64
    import requests

    if not os.path.exists(file_path):
        return f"Error: File not found at {file_path}"

    try:
        with open(file_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")

        prompt = (
            "You are an invoice data extractor. Look at this invoice image carefully.\n"
            "Extract ALL text and numbers you can see, preserving the exact values.\n"
            "List every field you can identify: invoice number, dates, sender details, "
            "receiver details, line items with quantities and prices, subtotal, tax, total.\n"
            "Copy numbers EXACTLY as shown — do not round or calculate.\n"
            "Output the raw extracted text in a structured format."
        )

        response = requests.post(
            f"{ollama_base_url}/api/chat",
            json={
                "model": "llava:7b",
                "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
                "stream": False,
            },
            timeout=120,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]
        return f"LLAVA_RESULT: HIGH CONFIDENCE (vision model).\n\nExtracted text:\n{content}"

    except Exception as e:
        return f"Error extracting image with LLaVA: {str(e)}"
