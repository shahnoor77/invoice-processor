import os
from crewai.tools import BaseTool
from typing import Type, Optional, List
from pydantic import BaseModel, Field
from invoice_processing_automation_system.fetch_latest_emails import fetch_latest_invoice_attachments


# ── Shared OCR helpers ────────────────────────────────────────────────────────

# Tesseract config tuned for invoice numbers and financial figures:
# preserve_interword_spaces keeps column alignment intact
TESS_CFG = (
    "--psm 6 --oem 3 "
    "-c preserve_interword_spaces=1 "
    "-c tessedit_char_whitelist="
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    "0123456789.,/:;-_()@#%&+= "
)


def _fix_ocr_spacing(text: str) -> str:
    """
    Fix common OCR spacing issues:
    - Restore spaces between words that got merged (CamelCase-like joins)
    - Fix spaces around numbers and currency symbols
    - Handle ligatures and font-specific merges
    """
    import re
    # Add space before uppercase letter following lowercase (e.g. "InvoiceNumber" → "Invoice Number")
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
    # Add space between letter and digit sequences where missing (e.g. "INV001" stays, "Total100" → "Total 100")
    text = re.sub(r'([A-Za-z]{2,})(\d)', r'\1 \2', text)
    text = re.sub(r'(\d)([A-Za-z]{2,})', r'\1 \2', text)
    # Normalize multiple spaces to single space
    text = re.sub(r' {2,}', ' ', text)
    # Fix lines that have no spaces at all (fully merged line) — skip short tokens
    lines = []
    for line in text.splitlines():
        if len(line) > 30 and ' ' not in line.strip():
            # Try to split on common invoice keywords
            for kw in ['Invoice', 'Date', 'Total', 'Amount', 'Tax', 'Subtotal', 'Due', 'From', 'To', 'Bank']:
                line = line.replace(kw, f' {kw} ')
            line = re.sub(r' {2,}', ' ', line).strip()
        lines.append(line)
    return '\n'.join(lines)


def _preprocess_for_ocr(img):
    """
    Shared image preprocessing pipeline for both PDF pages and standalone images.
    Optimised for invoice number / financial figure accuracy.
    """
    from PIL import ImageFilter, ImageEnhance
    import numpy as np

    # Upscale if too small — Tesseract needs ~300-400 DPI equivalent
    w, h = img.size
    if w < 2000 or h < 2000:
        scale = max(2000 / w, 2000 / h)
        from PIL import Image
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    # Light denoise — median filter removes salt-and-pepper without blurring digits
    img = img.filter(ImageFilter.MedianFilter(size=3))

    # Moderate sharpening — two passes is enough; over-sharpening breaks thin strokes
    img = img.filter(ImageFilter.SHARPEN)
    img = img.filter(ImageFilter.SHARPEN)

    # Contrast boost
    img = ImageEnhance.Contrast(img).enhance(2.5)

    # Otsu-style binarization using mean of min/max
    arr = np.array(img)
    threshold = int((int(arr.min()) + int(arr.max())) / 2)
    img = img.point(lambda p: 255 if p > threshold else 0)

    return img


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
            from PIL import Image
            import io

            tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if os.path.exists(tesseract_path):
                pytesseract.pytesseract.tesseract_cmd = tesseract_path

            doc = pymupdf.open(file_path)
            all_text = []
            all_confidences = []

            for i, page in enumerate(doc):
                # Render at 400 DPI for better number recognition
                mat = pymupdf.Matrix(400 / 72, 400 / 72)
                pix = page.get_pixmap(matrix=mat, colorspace=pymupdf.csGRAY)
                img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")

                img = _preprocess_for_ocr(img)

                data = pytesseract.image_to_data(img, config=TESS_CFG, output_type=pytesseract.Output.DICT)
                confs = [int(c) for c in data["conf"] if int(c) > 0]
                all_confidences.extend(confs)

                text = pytesseract.image_to_string(img, config=TESS_CFG)
                if text.strip():
                    all_text.append(f"--- Page {i+1} ---\n{text}")

            doc.close()

            if not all_text:
                return "PDF_RESULT: No text could be extracted. PDF may be corrupted or unreadable. Do NOT fabricate — mark all fields as null."

            avg_conf = sum(all_confidences) / len(all_confidences) if all_confidences else 0
            combined = _fix_ocr_spacing("\n\n".join(all_text))

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
            from PIL import Image

            # Set tesseract path for Windows if needed
            tesseract_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if os.path.exists(tesseract_path):
                pytesseract.pytesseract.tesseract_cmd = tesseract_path

            img = Image.open(file_path)
            # Handle palette images with transparency
            if img.mode in ("P", "PA"):
                img = img.convert("RGBA")
            img = img.convert("L")  # grayscale

            img = _preprocess_for_ocr(img)

            # Get OCR with confidence data
            data = pytesseract.image_to_data(img, config=TESS_CFG, output_type=pytesseract.Output.DICT)

            words = [w for w, c in zip(data["text"], data["conf"]) if w.strip() and int(c) > 0]
            confidences = [int(c) for c in data["conf"] if int(c) > 0]

            if not words:
                return "OCR_RESULT: No text could be extracted. Image may be too blurry or low quality. Do NOT fabricate any data — mark all fields as null."

            avg_conf = sum(confidences) / len(confidences) if confidences else 0
            text = _fix_ocr_spacing(pytesseract.image_to_string(img, config=TESS_CFG))

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


class GmailInvoiceFetcherInput(BaseModel):
    """Input schema for GmailInvoiceFetcher."""
    max_results: int = Field(
        default=5,
        description="Maximum number of latest emails to check."
    )
    query: Optional[str] = Field(
        default="in:inbox is:unread",
        description=(
            "Gmail search query to filter emails. "
            "Default fetches latest unread inbox emails."
        )
    )
    save_dir: str = Field(
        default="downloaded_attachments",
        description="Directory where invoice attachments will be saved."
    )


class GmailInvoiceFetcher(BaseTool):
    name: str = "gmail_invoice_fetcher"
    description: str = (
        "Fetches the latest Gmail emails with attachments, filters invoice attachments "
        "based on filename containing 'invoice', saves them locally, and returns "
        "a list of saved file paths."
    )
    args_schema: Type[BaseModel] = GmailInvoiceFetcherInput

    def _run(
        self,
        max_results: int = 5,
        query: Optional[str] = "in:inbox is:unread",
        save_dir: str = "downloaded_attachments"
    ) -> List[str]:
        try:
            file_paths = fetch_latest_invoice_attachments(
                max_results=max_results,
                query=query,
                save_dir=save_dir
            )
            return file_paths
        except Exception as e:
            return [f"Error fetching invoice attachments: {str(e)}"]