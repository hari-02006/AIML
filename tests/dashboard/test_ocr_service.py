"""
Unit and integration tests for OCR service (Stage 8).
Verifies engine availability, real OCR text recognition on images,
error handling for missing/invalid input, and format handling.
"""

import io
import pytest
from PIL import Image, ImageDraw
from frontend.utils.ocr_service import (
    perform_ocr,
    is_ocr_available,
    get_available_engines,
    preprocess_image_for_ocr
)

def create_text_image(text_lines, size=(600, 250), bg_color=(255, 255, 255), text_color=(0, 0, 0)) -> bytes:
    """Helper to generate a clean synthetic invoice image in memory."""
    img = Image.new("RGB", size, color=bg_color)
    draw = ImageDraw.Draw(img)
    y = 25
    for line in text_lines:
        draw.text((25, y), line, fill=text_color)
        y += 35
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def test_ocr_engine_detection():
    """Verify that the system detects at least one local OCR engine."""
    engines = get_available_engines()
    assert isinstance(engines, list)
    # On Windows 10/11, Windows Media OCR is present natively
    assert len(engines) > 0, "Expected at least one local OCR engine (Windows Media OCR or Tesseract)"
    assert is_ocr_available() is True

def test_ocr_none_input():
    """Verify graceful error return when None is supplied."""
    res = perform_ocr(None)
    assert res["success"] is False
    assert "No image input provided" in res["error"]
    assert res["raw_text"] == ""

def test_ocr_invalid_input_type():
    """Verify graceful handling of unsupported input types."""
    res = perform_ocr(12345)
    assert res["success"] is False
    assert "Unsupported image input type" in res["error"]

def test_ocr_corrupted_bytes():
    """Verify graceful handling when non-image bytes are supplied."""
    res = perform_ocr(b"Not an image at all")
    assert res["success"] is False
    assert "Failed to load image" in res["error"]

def test_preprocess_image():
    """Verify image pre-processing scales small images properly."""
    small_img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    processed = preprocess_image_for_ocr(small_img)
    assert processed.width >= 1000 or processed.height >= 1000

def test_real_ocr_execution_on_invoice_image():
    """
    REAL OCR ENGINE EXECUTION TEST:
    Feeds a real rendered image into the local OCR engine and verifies
    actual optical character recognition output.
    """
    invoice_lines = [
        "INVOICE NUMBER: INV-2025-9901",
        "DATE: 20-08-2025",
        "VENDOR: STAR ELECTRONICS LTD",
        "TOTAL AMOUNT: 14500.00"
    ]
    img_bytes = create_text_image(invoice_lines, size=(700, 250))
    res = perform_ocr(img_bytes)

    assert res["success"] is True
    assert res["error"] is None
    assert len(res["raw_text"]) > 0
    assert res["word_count"] > 0
    assert len(res["lines"]) > 0
    assert "Windows Media OCR" in res["engine"] or "Tesseract" in res["engine"]

    # Verify key text is recognized by the OCR engine
    raw_upper = res["raw_text"].upper()
    assert any(term in raw_upper for term in ["INV", "2025", "STAR", "TOTAL", "AMOUNT", "14500"])


# -------------------------------------------------------------------------
# Stage 8 Regression Tests: Keyword Compatibility & Failure Reporting
# -------------------------------------------------------------------------

def test_perform_ocr_accepts_filename_keyword():
    """
    REGRESSION TEST: Verify perform_ocr accepts filename keyword argument
    without raising TypeError: perform_ocr() got an unexpected keyword argument 'filename'.
    """
    invoice_lines = ["INVOICE # 1001", "TOTAL: 500.00"]
    img_bytes = create_text_image(invoice_lines)

    # Must accept filename=... as a keyword argument across engines
    res1 = perform_ocr(img_bytes, filename="invoice_scan.png")
    assert isinstance(res1, dict)
    assert "success" in res1

    res2 = perform_ocr(img_bytes, preferred_engine="winocr", filename="document.tiff")
    assert isinstance(res2, dict)
    assert "success" in res2


def test_perform_ocr_passes_filename_to_paddleocr_service(monkeypatch):
    """
    Verify that perform_ocr forwards the filename parameter to predict_document_paddleocr.
    """
    captured_args = {}

    def mock_predict(image_input, filename=None):
        captured_args["filename"] = filename
        return {
            "success": True,
            "raw_text": "Sample text",
            "lines": ["Sample text"],
            "layout_lines": ["Sample text"],
            "total_words": 2,
            "total_lines": 1,
            "page_count": 1,
            "pages": [],
            "markdown": "Sample",
            "metadata": {},
            "summary": {},
            "line_items": [],
            "reconciliation": {}
        }

    import frontend.utils.paddleocr_vl_service as pservice
    monkeypatch.setattr(pservice, "predict_document_paddleocr", mock_predict)

    res = perform_ocr(b"dummy_bytes", preferred_engine="paddleocr", filename="vendor_bill.pdf")
    assert res["success"] is True
    assert captured_args.get("filename") == "vendor_bill.pdf"
    assert res["engine"] == "PaddleOCR-VL 1.6 (Local VLM)"


def test_paddleocr_failure_does_not_silently_fallback_to_winocr(monkeypatch):
    """
    REGRESSION TEST: If PaddleOCR fails or times out, perform_ocr must report
    the actual PaddleOCR error and NOT silently fall back to Windows Media OCR.
    """
    def mock_predict_fail(image_input, filename=None):
        return {
            "success": False,
            "error": "PaddleOCR-VL inference timed out after 180 seconds."
        }

    import frontend.utils.paddleocr_vl_service as pservice
    monkeypatch.setattr(pservice, "predict_document_paddleocr", mock_predict_fail)

    res = perform_ocr(b"dummy_bytes", preferred_engine="PaddleOCR-VL 1.6 (Local VLM)")
    assert res["success"] is False
    assert "timed out after 180 seconds" in res["error"]
    assert res["engine"] == "PaddleOCR-VL 1.6 (Local VLM)"


def test_round_off_sign_provenance_and_derived_reconciliation():
    """
    REGRESSION TEST: Verify that:
    1. Ambiguous label (+/-) preserves recognized magnitude (0.20) and marks source as ambiguous.
    2. Derived adjustment is distinct (-0.20).
    3. Explicit negative sign is recognized directly as negative.
    """
    from frontend.utils.paddleocr_vl_worker import extract_tables_and_items, audit_discrepancies

    # Case A: Ambiguous printed label (+/-) with positive magnitude 0.20
    html_ambiguous = """
    <table>
      <tr><td>Product 1</td><td>1</td><td>100.20</td><td>100.20</td></tr>
      <tr><td>Subtotal</td><td>100.20</td></tr>
      <tr><td>Round off (+/-):</td><td>0.20</td></tr>
      <tr><td>Total Amount :</td><td>100.00</td></tr>
    </table>
    """
    items_a, summary_a, _ = extract_tables_and_items(html_ambiguous)
    audit_a = audit_discrepancies(summary_a, items_a)

    assert summary_a["round_off"] == 0.20
    assert summary_a["recognized_round_off"] == 0.20
    assert summary_a["round_off_sign_source"] == "ambiguous_label"
    assert summary_a["derived_round_off"] == -0.20
    assert audit_a["status"] == "Reconciled with Round-Off"
    assert audit_a["derived_adjustment"] == -0.20
    assert audit_a["recognized_round_off"] == 0.20
    assert "Ambiguous sign in print" in audit_a["notes"][0]

    # Case B: Explicit negative value -0.20
    html_explicit = """
    <table>
      <tr><td>Product 1</td><td>1</td><td>100.20</td><td>100.20</td></tr>
      <tr><td>Subtotal</td><td>100.20</td></tr>
      <tr><td>Round off:</td><td>-0.20</td></tr>
      <tr><td>Total Amount :</td><td>100.00</td></tr>
    </table>
    """
    items_b, summary_b, _ = extract_tables_and_items(html_explicit)
    assert summary_b["round_off"] == -0.20
    assert summary_b["round_off_sign_source"] == "explicit_negative"


def test_app_imports_ocr_availability_functions():
    """
    Regression test: Verify that frontend.app successfully imports
    check_winocr_available and check_tesseract_available without NameError.
    """
    import frontend.app as app
    assert hasattr(app, "check_winocr_available")
    assert hasattr(app, "check_tesseract_available")
    assert callable(app.check_winocr_available)
    assert callable(app.check_tesseract_available)

    win_avail, win_langs = app.check_winocr_available()
    assert isinstance(win_avail, bool)
    assert isinstance(win_langs, list)


def test_ocr_availability_when_winocr_unavailable(monkeypatch):
    """
    Verify clean boolean and diagnostic behavior when Windows OCR is not available.
    Must return (False, []) and not raise NameError or unhandled exception.
    """
    from frontend.utils.ocr_service import check_winocr_available
    import sys

    # Simulate winrt not installed/available
    monkeypatch.setitem(sys.modules, "winrt.windows.media.ocr", None)

    # When imported module is None, check_winocr_available must return (False, [])
    win_avail, langs = check_winocr_available()
    assert win_avail is False
    assert langs == []


