"""
Unit and integration tests for PaddleOCR-VL 1.6 Service & Multi-Page Extraction (Stage 8).
Verifies:
- PDF and TIFF validation
- HTML table & line-item extraction
- European VAT and Indian GST table structures
- Mathematical audit & reconciliation (round-off, one-cent variance, discrepancies)
- Server health checking and fallback mechanics
"""

import io
import pytest
from PIL import Image
from frontend.utils.image_validator import validate_invoice_image, SUPPORTED_EXTENSIONS
from frontend.utils.paddleocr_vl_worker import (
    extract_tables_and_items,
    extract_metadata_from_markdown,
    audit_discrepancies,
    clean_amount,
    process_document
)
from frontend.utils.paddleocr_vl_service import (
    is_paddleocr_available,
    check_server_health,
    get_paddleocr_python_path
)
from frontend.utils.ocr_service import perform_ocr, get_available_engines


# -------------------------------------------------------------------------
# 1. Document Format & Multi-Page Validation Tests
# -------------------------------------------------------------------------

def test_supported_extensions_includes_pdf_and_tiff():
    """Verify that PDF and TIFF extensions are supported."""
    assert ".pdf" in SUPPORTED_EXTENSIONS
    assert ".tiff" in SUPPORTED_EXTENSIONS
    assert ".tif" in SUPPORTED_EXTENSIONS
    assert ".png" in SUPPORTED_EXTENSIONS
    assert ".jpg" in SUPPORTED_EXTENSIONS


def test_validate_invoice_image_pdf():
    """Verify PDF validation and page count detection."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument.new()
    pdf.new_page(width=612, height=792)
    pdf.new_page(width=612, height=792)
    buf = io.BytesIO()
    pdf.save(buf)
    pdf_bytes = buf.getvalue()

    is_valid, msg, meta = validate_invoice_image(pdf_bytes, filename="invoice_doc.pdf")
    assert is_valid is True
    assert meta["format"] == "PDF"
    assert meta["page_count"] == 2
    assert meta["width"] == 612
    assert meta["height"] == 792


def test_validate_invoice_image_tiff():
    """Verify TIFF image validation."""
    img = Image.new("RGB", (300, 400), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="TIFF")
    tiff_bytes = buf.getvalue()

    is_valid, msg, meta = validate_invoice_image(tiff_bytes, filename="invoice.tiff")
    assert is_valid is True
    assert meta["format"] == "TIFF"
    assert meta["width"] == 300
    assert meta["height"] == 400


# -------------------------------------------------------------------------
# 2. HTML Table & Line Item Extraction Tests
# -------------------------------------------------------------------------

def test_extract_european_vat_table_and_summary():
    """Verify table parser on European VAT invoice structure."""
    html_content = """
    <table>
      <tr><td>No.</td><td>Description</td><td>Qty</td><td>UM</td><td>Net price</td><td>Net worth</td><td>VAT [%]</td><td>Gross worth</td></tr>
      <tr><td>1.</td><td>Dell Desktop Computer PC</td><td>3,00</td><td>each</td><td>209,00</td><td>627,00</td><td>10%</td><td>689,70</td></tr>
      <tr><td>2.</td><td>Thin Client Computer</td><td>5,00</td><td>each</td><td>37,75</td><td>188,75</td><td>10%</td><td>207,63</td></tr>
    </table>
    <table>
      <tr><td></td><td>VAT [%]</td><td>Net worth</td><td>VAT</td><td>Gross worth</td></tr>
      <tr><td></td><td>10%</td><td>5 640,17</td><td>564,02</td><td>6 204,19</td></tr>
      <tr><td>Total</td><td></td><td>$ 5 640,17</td><td>$ 564,02</td><td>$ 6 204,19</td></tr>
    </table>
    """
    items, summary, tables = extract_tables_and_items(html_content, page_num=1)

    assert len(items) == 2
    assert items[0]["description"] == "Dell Desktop Computer PC"
    assert items[0]["quantity"] == 3.0
    assert items[0]["unit_price"] == 209.0
    assert items[0]["taxable_amount"] == 627.0
    assert items[0]["tax_rate"] == "10%"
    assert items[0]["total"] == 689.70

    assert items[1]["description"] == "Thin Client Computer"
    assert items[1]["taxable_amount"] == 188.75
    assert items[1]["total"] == 207.63

    assert summary.get("subtotal") == 5640.17
    assert summary.get("vat_amount") == 564.02
    assert summary.get("grand_total") == 6204.19


def test_extract_indian_gst_table_and_summary():
    """Verify table parser on Indian GST invoice structure with colspan & tax splits."""
    html_content = """
    <table>
      <tr><td>Billed To</td><td># Inv. No. :</td><td>Inv-4</td></tr>
      <tr><td>Name :</td><td>Sample Customer</td><td>Inv. Date :</td><td>17-Dec-24</td></tr>
      <tr><td>GSTIN :</td><td>07ASD025SDF</td><td>Terms :</td><td>Immediate</td></tr>
      <tr><td>SN</td><td>PRODUCT DISCRIPION</td><td>HSN</td><td>Qty.</td><td>Rate</td><td>Taxable</td><td>GST %</td><td>GST Amt.</td><td>Total</td></tr>
      <tr><td>1</td><td>Televisions LED Smart TV</td><td>4589</td><td>1</td><td>13000.00</td><td>13000.00</td><td>18%</td><td>2340.00</td><td>15,340.00</td></tr>
      <tr><td>2</td><td>Portable Bluetooth Speaker</td><td>2055</td><td>2</td><td>520.00</td><td>1040.00</td><td>18%</td><td>187.20</td><td>1,227.20</td></tr>
      <tr><td>Sub-Total:</td><td>3</td><td>14040.00</td><td>2527.20</td><td>16567.20</td></tr>
      <tr><td>Our Bank Details</td><td>SUMMERY</td><td>AMOUNT</td></tr>
      <tr><td>Bank Name :</td><td>STATE BANK OF INDIA</td><td>CGST Amt :</td><td>1,263.60</td></tr>
      <tr><td>Account No :</td><td>20412XXXX06</td><td>SGST Amt :</td><td>1,263.60</td></tr>
      <tr><td>IFSC Code :</td><td>SBIN003XXXX9</td><td>Round off (+/-):</td><td>0.20</td></tr>
      <tr><td>Invoice Total in Word</td><td>Total Amount :</td><td>16,567.00</td></tr>
    </table>
    """
    items, summary, tables = extract_tables_and_items(html_content, page_num=1)

    assert len(items) == 2
    assert items[0]["description"] == "Televisions LED Smart TV"
    assert items[0]["hsn_sac"] == "4589"
    assert items[0]["quantity"] == 1.0
    assert items[0]["unit_price"] == 13000.0
    assert items[0]["taxable_amount"] == 13000.0
    assert items[0]["tax_rate"] == "18%"
    assert items[0]["tax_amount"] == 2340.0
    assert items[0]["total"] == 15340.0

    assert items[1]["description"] == "Portable Bluetooth Speaker"
    assert items[1]["hsn_sac"] == "2055"
    assert items[1]["quantity"] == 2.0
    assert items[1]["unit_price"] == 520.0
    assert items[1]["taxable_amount"] == 1040.0
    assert items[1]["tax_amount"] == 187.20
    assert items[1]["total"] == 1227.20

    assert summary.get("cgst_amount") == 1263.60
    assert summary.get("sgst_amount") == 1263.60
    assert summary.get("round_off") == 0.20
    assert summary.get("recognized_round_off") == 0.20
    assert summary.get("round_off_sign_source") == "ambiguous_label"
    assert summary.get("derived_round_off") == -0.20
    assert summary.get("grand_total") == 16567.00
    assert summary.get("bank_name") == "STATE BANK OF INDIA"


# -------------------------------------------------------------------------
# 3. Mathematical Audit & Reconciliation Tests
# -------------------------------------------------------------------------

def test_audit_discrepancies_exact_match():
    """Verify exact match reconciliation."""
    summary = {"grand_total": 500.00, "subtotal": 450.00}
    items = [
        {"total": 200.00, "taxable_amount": 180.00},
        {"total": 300.00, "taxable_amount": 270.00}
    ]
    audit = audit_discrepancies(summary, items)
    assert audit["status"] == "Exact Match"
    assert audit["discrepancy_amount"] == 0.0


def test_audit_discrepancies_minor_one_cent_variance():
    """Verify preservation of printed total and reporting of 1-cent tax rounding variance."""
    summary = {"grand_total": 6204.19, "subtotal": 5640.17}
    items = [
        {"total": 689.70, "taxable_amount": 627.00},
        {"total": 207.63, "taxable_amount": 188.75},
        {"total": 440.00, "taxable_amount": 400.00},
        {"total": 1534.14, "taxable_amount": 1394.67},
        {"total": 1220.95, "taxable_amount": 1109.95},
        {"total": 1187.78, "taxable_amount": 1079.80},
        {"total": 924.00, "taxable_amount": 840.00}
    ]
    # Sum of items is 6,204.20
    audit = audit_discrepancies(summary, items)
    assert audit["status"] == "Minor Rounding Variance (Preserved)"
    assert audit["discrepancy_amount"] == 0.01
    assert "differs by +0.01" in audit["notes"][0]


def test_audit_discrepancies_round_off_reconciliation():
    """Verify round-off reconciliation for GST invoices."""
    summary = {"grand_total": 46415.00, "round_off": -0.20}
    items = [
        {"total": 46415.20, "taxable_amount": 41440.00}
    ]
    audit = audit_discrepancies(summary, items)
    assert "Round-Off" in audit["status"]


def test_audit_discrepancies_large_mismatch():
    """Verify discrepancy detection when item sum significantly deviates from printed grand total."""
    summary = {"grand_total": 10000.00}
    items = [
        {"total": 4000.00, "taxable_amount": 3500.00}
    ]
    audit = audit_discrepancies(summary, items)
    assert audit["status"] == "Discrepancy Detected"
    assert audit["discrepancy_amount"] == -6000.00


# -------------------------------------------------------------------------
# 4. PaddleOCR-VL Service & Engine Tests
# -------------------------------------------------------------------------

def test_paddleocr_environment_detected():
    """Verify that isolated .venv_paddleocr and worker script are discovered."""
    py_path = get_paddleocr_python_path()
    if py_path is None:
        pytest.skip("Optional PaddleOCR-VL environment is unavailable")
    assert is_paddleocr_available() is True


def test_get_available_engines_includes_paddleocr(monkeypatch):
    """Verify that get_available_engines lists PaddleOCR-VL 1.6."""
    from frontend.utils import ocr_service, paddleocr_vl_service

    monkeypatch.setattr(paddleocr_vl_service, "is_paddleocr_available", lambda: True)
    monkeypatch.setattr(ocr_service, "check_winocr_available", lambda: (True, ["en-US"]))
    engines = get_available_engines()
    assert "PaddleOCR-VL 1.6 (Local VLM)" in engines
    assert "Windows Media OCR (Local)" in engines


def test_perform_ocr_fallback_winocr_executes():
    """Verify that perform_ocr with preferred_engine='winocr' executes instantly and reliably."""
    from PIL import ImageDraw
    img = Image.new("RGB", (600, 200), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), "INVOICE # 987654", fill=(0, 0, 0))
    draw.text((20, 70), "TOTAL: 500.00", fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    res = perform_ocr(buf.getvalue(), preferred_engine="winocr")
    assert res["success"] is True
    assert "Windows Media OCR" in res["engine"]
    assert res["word_count"] > 0


# -------------------------------------------------------------------------
# 5. Lightweight Mocked Multi-Page Integration Tests
# -------------------------------------------------------------------------

class MockPipeline:
    def __init__(self, responses):
        self.responses = responses
        self.call_count = 0
        self.received_images = []

    def predict(self, img_np):
        self.call_count += 1
        self.received_images.append(img_np)
        idx = self.call_count - 1
        if idx < len(self.responses):
            resp = self.responses[idx]
            if isinstance(resp, Exception):
                raise resp
            return resp
        return []


class MockPageOutput:
    def __init__(self, markdown_text, parsing_list=None):
        self.markdown = {"markdown_texts": markdown_text}
        self.parsing_res_list = parsing_list or []

    def get(self, key, default=None):
        if key == "parsing_res_list":
            return self.parsing_res_list
        return default


def test_multipage_pdf_dispatch_and_order_preserved():
    """Verify that every PDF page is dispatched to OCR and page order is strictly preserved."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument.new()
    pdf.new_page(width=612, height=792)
    pdf.new_page(width=612, height=792)
    buf = io.BytesIO()
    pdf.save(buf)
    pdf_bytes = buf.getvalue()

    p1_md = "Invoice No: INV-PAGE-1\n\n<table><tr><td>No.</td><td>Description</td><td>Qty</td><td>Rate</td><td>Total</td></tr><tr><td>1</td><td>Widget A</td><td>2</td><td>50.00</td><td>100.00</td></tr></table>"
    p2_md = "Page 2 continued\n\n<table><tr><td>No.</td><td>Description</td><td>Qty</td><td>Rate</td><td>Total</td></tr><tr><td>2</td><td>Widget B</td><td>3</td><td>40.00</td><td>120.00</td></tr></table>"

    mock_pipe = MockPipeline([
        [MockPageOutput(p1_md)],
        [MockPageOutput(p2_md)]
    ])

    res = process_document(pdf_bytes, filename="multi_test.pdf", pipeline=mock_pipe)

    assert res["success"] is True
    assert mock_pipe.call_count == 2
    assert res["page_count"] == 2
    assert len(res["pages"]) == 2
    assert res["pages"][0]["page_number"] == 1
    assert res["pages"][1]["page_number"] == 2
    assert "INV-PAGE-1" in res["pages"][0]["markdown"]
    assert "Page 2 continued" in res["pages"][1]["markdown"]
    assert len(res["line_items"]) == 2
    assert res["line_items"][0]["description"] == "Widget A"
    assert res["line_items"][0]["page"] == 1
    assert res["line_items"][1]["description"] == "Widget B"
    assert res["line_items"][1]["page"] == 2


def test_multipage_error_identifies_failing_page_and_no_partial_document():
    """Verify that a failure on a later page returns an error identifying the page and does not present partial results as success."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument.new()
    pdf.new_page(width=612, height=792)
    pdf.new_page(width=612, height=792)
    buf = io.BytesIO()
    pdf.save(buf)
    pdf_bytes = buf.getvalue()

    p1_md = "<table><tr><td>No.</td><td>Description</td><td>Qty</td><td>Rate</td><td>Total</td></tr><tr><td>1</td><td>Widget A</td><td>2</td><td>50.00</td><td>100.00</td></tr></table>"
    
    mock_pipe = MockPipeline([
        [MockPageOutput(p1_md)],
        RuntimeError("Memory error while decoding visual tokens")
    ])

    res = process_document(pdf_bytes, filename="fail_page2.pdf", pipeline=mock_pipe)

    assert res["success"] is False
    assert res["failed_page"] == 2
    assert res["total_pages"] == 2
    assert "Failed to process page 2 of 2" in res["error"]
    assert "Memory error" in res["error"]


def test_multipage_table_continuation_skips_repeated_headers():
    """Verify that a continued line-item table does not duplicate line items when subsequent pages repeat the header row."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument.new()
    pdf.new_page(width=612, height=792)
    pdf.new_page(width=612, height=792)
    buf = io.BytesIO()
    pdf.save(buf)
    pdf_bytes = buf.getvalue()

    p1_md = "<table><tr><td>No.</td><td>Description</td><td>Qty</td><td>Rate</td><td>Total</td></tr><tr><td>1</td><td>Monitor 27in</td><td>1</td><td>250.00</td><td>250.00</td></tr></table>"
    p2_md = "<table><tr><td>No.</td><td>Description</td><td>Qty</td><td>Rate</td><td>Total</td></tr><tr><td>2</td><td>Keyboard Mech</td><td>2</td><td>75.00</td><td>150.00</td></tr></table>"

    mock_pipe = MockPipeline([
        [MockPageOutput(p1_md)],
        [MockPageOutput(p2_md)]
    ])

    res = process_document(pdf_bytes, filename="continued.pdf", pipeline=mock_pipe)

    assert res["success"] is True
    assert len(res["line_items"]) == 2
    descriptions = [item["description"] for item in res["line_items"]]
    assert descriptions == ["Monitor 27in", "Keyboard Mech"]
    assert "Description" not in descriptions


def test_multipage_tiff_frame_order_preserved():
    """Verify that multi-frame TIFFs process all frames and strictly preserve frame order."""
    frame1 = Image.new("RGB", (400, 300), color=(200, 200, 200))
    frame2 = Image.new("RGB", (400, 300), color=(150, 150, 150))
    buf = io.BytesIO()
    frame1.save(buf, format="TIFF", save_all=True, append_images=[frame2])
    tiff_bytes = buf.getvalue()

    p1_md = "Page 1 Content\n<table><tr><td>No.</td><td>Description</td><td>Qty</td><td>Rate</td><td>Total</td></tr><tr><td>1</td><td>Item One</td><td>1</td><td>10.00</td><td>10.00</td></tr></table>"
    p2_md = "Page 2 Content\n<table><tr><td>No.</td><td>Description</td><td>Qty</td><td>Rate</td><td>Total</td></tr><tr><td>2</td><td>Item Two</td><td>1</td><td>20.00</td><td>20.00</td></tr></table>"

    mock_pipe = MockPipeline([
        [MockPageOutput(p1_md)],
        [MockPageOutput(p2_md)]
    ])

    res = process_document(tiff_bytes, filename="scan.tiff", pipeline=mock_pipe)

    assert res["success"] is True
    assert mock_pipe.call_count == 2
    assert res["page_count"] == 2
    assert res["pages"][0]["page_number"] == 1
    assert "Page 1 Content" in res["pages"][0]["markdown"]
    assert res["pages"][1]["page_number"] == 2
    assert "Page 2 Content" in res["pages"][1]["markdown"]


def test_real_gst_invoice_structure_from_ocr_output():
    """Verify parser accuracy on the exact HTML table structure produced by PaddleOCR-VL from real invoice.png."""
    import os
    gpu_pred_path = os.path.join(os.path.dirname(__file__), "..", "..", "invoice_gpu_predict.json")
    if not os.path.exists(gpu_pred_path):
        pytest.skip("Private invoice fixture is only available locally")
    if os.path.exists(gpu_pred_path):
        import json
        with open(gpu_pred_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["success"] is True
        assert len(data["line_items"]) == 7
        assert data["metadata"]["invoice_number"] == "Inv-4"
        assert data["metadata"]["invoice_date"] == "17-Dec-24"
        assert data["metadata"]["seller_name"]
        assert data["metadata"]["buyer_name"]
        assert data["summary"]["grand_total"] == 46415.00
        assert data["summary"]["subtotal"] == 41440.00
        assert data["summary"]["cgst_amount"] == 2487.60
        assert data["summary"]["sgst_amount"] == 2487.60
        assert data["summary"]["round_off"] == 0.20
        assert data["summary"]["recognized_round_off"] == 0.20
        assert data["summary"]["round_off_sign_source"] == "ambiguous_label"
        assert data["summary"]["derived_round_off"] == -0.20
        assert data["reconciliation"]["status"] == "Reconciled with Round-Off"
        assert data["reconciliation"]["discrepancy_amount"] == -0.20
        assert data["reconciliation"]["derived_adjustment"] == -0.20
        assert "(-0.20)" in data["reconciliation"]["notes"][0]

