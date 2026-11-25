"""
Unit tests for Stage 7 Invoice Scanning interface validation logic.
Tests supported image formats (JPG, JPEG, PNG), invalid/corrupted files,
size boundaries, and document types.
"""

import io
import pytest
from PIL import Image
from frontend.utils.image_validator import (
    validate_invoice_image,
    DOCUMENT_TYPES,
    MAX_FILE_SIZE_BYTES
)

def create_sample_image(img_format="JPEG", size=(200, 200), color=(255, 0, 0)) -> bytes:
    """Helper to generate in-memory dummy image bytes."""
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format=img_format)
    return buf.getvalue()

def test_document_types_complete():
    """Verify all required document types are present."""
    expected_types = [
        "Supplier Invoice",
        "Goods-Received Document",
        "Customer Sales Invoice"
    ]
    for doc_type in expected_types:
        assert doc_type in DOCUMENT_TYPES, f"Missing document type: {doc_type}"

def test_validate_valid_jpeg():
    """Test valid JPEG image bytes and filename."""
    jpeg_bytes = create_sample_image(img_format="JPEG")
    is_valid, msg, meta = validate_invoice_image(jpeg_bytes, filename="invoice_01.jpg")
    assert is_valid is True
    assert msg == "Valid invoice image."
    assert meta is not None
    assert meta["format"] == "JPEG"
    assert meta["width"] == 200
    assert meta["height"] == 200
    assert meta["size_bytes"] > 0

def test_validate_valid_png():
    """Test valid PNG image bytes and filename."""
    png_bytes = create_sample_image(img_format="PNG")
    is_valid, msg, meta = validate_invoice_image(png_bytes, filename="bill_scan.png")
    assert is_valid is True
    assert meta["format"] == "PNG"

def test_validate_empty_bytes():
    """Test validation fails gracefully on empty file bytes."""
    is_valid, msg, meta = validate_invoice_image(b"", filename="empty.jpg")
    assert is_valid is False
    assert "No image data detected" in msg
    assert meta is None

def test_validate_unsupported_extension():
    """Test validation fails for unsupported file extensions like .txt or .docx."""
    sample_bytes = create_sample_image(img_format="JPEG")
    is_valid, msg, meta = validate_invoice_image(sample_bytes, filename="invoice.txt")
    assert is_valid is False
    assert "Unsupported file extension" in msg

def test_validate_corrupted_image():
    """Test validation fails on invalid or corrupted byte payloads."""
    corrupted_bytes = b"This is not a real image header or content."
    is_valid, msg, meta = validate_invoice_image(corrupted_bytes, filename="broken.jpg")
    assert is_valid is False
    assert "Corrupted or invalid image" in msg

def test_validate_oversized_file():
    """Test validation fails if file exceeds maximum allowed size."""
    oversized_bytes = b"0" * (MAX_FILE_SIZE_BYTES + 1024)
    is_valid, msg, meta = validate_invoice_image(oversized_bytes, filename="huge.jpg")
    assert is_valid is False
    assert "exceeds maximum allowed limit" in msg
