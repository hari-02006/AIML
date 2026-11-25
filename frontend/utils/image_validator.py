"""
Validation utility for invoice uploads and camera captures.
Validates file formats, extensions, integrity, page counts, and size limits.
Supports multi-page PDFs, TIFFs, JPG, and PNG images.
"""

import io
import os
from typing import Tuple, Optional, Dict, Any
from PIL import Image

SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.pdf', '.tiff', '.tif'}
SUPPORTED_IMAGE_FORMATS = {'JPEG', 'PNG', 'TIFF'}
MAX_FILE_SIZE_MB = 25
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

DOCUMENT_TYPES = [
    "Supplier Invoice",
    "Goods-Received Document",
    "Customer Sales Invoice"
]

def validate_invoice_image(
    file_bytes: bytes,
    filename: Optional[str] = None
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """
    Validates invoice file bytes and optional filename.
    Supports single and multi-page documents (PDF, TIFF, JPG, PNG).

    Returns:
        (is_valid, message, metadata)
    """
    if not file_bytes:
        return False, "No image data detected. Please capture or upload an invoice file.", None

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        size_mb = len(file_bytes) / (1024 * 1024)
        return False, f"File size ({size_mb:.2f} MB) exceeds maximum allowed limit of {MAX_FILE_SIZE_MB} MB.", None

    ext = os.path.splitext(filename)[1].lower() if filename else ""
    if filename and ext and ext not in SUPPORTED_EXTENSIONS:
        return False, f"Unsupported file extension '{ext}'. Supported formats: PDF, TIFF, JPG, JPEG, and PNG.", None

    size_kb = round(len(file_bytes) / 1024, 2)

    # 1. Check for PDF Document
    if ext == ".pdf" or file_bytes.startswith(b"%PDF"):
        try:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(file_bytes)
            page_count = len(pdf)
            if page_count == 0:
                return False, "PDF document contains no readable pages.", None

            # Get first page dimensions
            first_page = pdf[0]
            width, height = int(first_page.get_width()), int(first_page.get_height())

            metadata = {
                "format": "PDF",
                "width": width,
                "height": height,
                "page_count": page_count,
                "size_bytes": len(file_bytes),
                "size_kb": size_kb
            }
            return True, f"Valid PDF invoice document ({page_count} page{'s' if page_count > 1 else ''}).", metadata

        except Exception as exc:
            return False, f"Corrupted or invalid PDF document: {str(exc)}", None

    # 2. Check for Image formats (JPEG, PNG, TIFF)
    try:
        image_stream = io.BytesIO(file_bytes)
        with Image.open(image_stream) as img:
            img_format = (img.format or "").upper()
            if img_format not in SUPPORTED_IMAGE_FORMATS:
                return False, f"Unsupported image format '{img_format}'. Supported formats: PDF, TIFF, JPG, and PNG.", None

            width, height = img.size
            page_count = getattr(img, "n_frames", 1)
            img.verify()

        metadata = {
            "format": img_format,
            "width": width,
            "height": height,
            "page_count": page_count,
            "size_bytes": len(file_bytes),
            "size_kb": size_kb
        }
        return True, "Valid invoice image.", metadata

    except Exception as exc:
        return False, f"Corrupted or invalid image file: {str(exc)}", None
