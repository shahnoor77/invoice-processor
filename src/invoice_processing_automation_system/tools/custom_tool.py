import os
from crewai.tools import BaseTool
from typing import Type, Optional, List
from pydantic import BaseModel, Field
from invoice_processing_automation_system.fetch_latest_emails import fetch_latest_invoice_attachments

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

            img = Image.open(file_path).convert("L")  # grayscale

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