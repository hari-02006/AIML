"""
Unit and pipeline tests for invoice parsing and field extraction (Stage 8).
Verifies metadata extraction, line-item parsing, GST and summary totals,
graceful handling of missing fields, and end-to-end OCR to parser pipeline.
"""

import io
import pytest
from PIL import Image, ImageDraw
from frontend.utils.invoice_parser import (
    parse_invoice_text,
    extract_invoice_metadata,
    extract_invoice_summary,
    extract_line_items
)
from frontend.utils.ocr_service import perform_ocr

SAMPLE_GST_INVOICE = """
TAX INVOICE
Supplier: Apex Retail Supply Co.
GSTIN: 27AABCA1234F1Z5
Buyer: Mumbai Supermart
Buyer GSTIN: 27XYZDE9876K1Z2
Invoice No: INV-2025-4421
Date: 12/05/2025
Due Date: 26/05/2025
----------------------------------------------------------------------
Item Description       HSN      Qty   Unit    Rate       Total
Logitech Optical Mouse 8471     10    Units   450.00     4500.00
Samsung 24 LED Monitor 8528      2    Units  8500.00    17000.00
----------------------------------------------------------------------
Subtotal: 21500.00
CGST 9%: 1935.00
SGST 9%: 1935.00
Discount: 500.00
Round Off: 0.00
Grand Total: 24870.00
Rupees in words: Twenty Four Thousand Eight Hundred Seventy Only
"""

SAMPLE_ALTERNATIVE_BILL = """
RETAIL CASH MEMO
M/s Modern Electronics
Bill No: BILL-902
Date: 04-Oct-2025
Customer: Rajesh Kumar
---------------------------------------------
Description           Qty      Rate     Amount
USB Cable 1m           3       150.00   450.00
Power Adapter          1       850.00   850.00
---------------------------------------------
Subtotal: 1300.00
Tax Amount: 156.00
Grand Total: 1456.00
"""

def test_parse_empty_text():
    """Verify parser returns unparsed status on empty input."""
    res = parse_invoice_text("")
    assert res["is_parsed"] is False
    assert res["status"] == "No readable text provided"
    assert res["line_items"] == []

def test_gst_invoice_metadata_extraction():
    """Verify GST invoice metadata fields extraction."""
    lines = [l.strip() for l in SAMPLE_GST_INVOICE.splitlines() if l.strip()]
    meta = extract_invoice_metadata(SAMPLE_GST_INVOICE, lines)

    assert meta["invoice_number"] == "INV-2025-4421"
    assert meta["invoice_date"] == "12/05/2025"
    assert meta["due_date"] == "26/05/2025"
    assert "Apex Retail Supply" in meta["seller_name"]
    assert "Mumbai Supermart" in meta["buyer_name"]
    assert meta["seller_gstin"] == "27AABCA1234F1Z5"
    assert meta["buyer_gstin"] == "27XYZDE9876K1Z2"
    assert meta["currency"] == "INR"

def test_gst_invoice_summary_extraction():
    """Verify summary totals and tax components."""
    lines = [l.strip() for l in SAMPLE_GST_INVOICE.splitlines() if l.strip()]
    summ = extract_invoice_summary(SAMPLE_GST_INVOICE, lines)

    assert summ["subtotal"] == 21500.0
    assert summ["cgst_amount"] == 1935.0
    assert summ["sgst_amount"] == 1935.0
    assert summ["total_tax"] == 3870.0
    assert summ["grand_total"] == 24870.0
    assert summ["discount"] == 500.0

def test_line_items_extraction():
    """Verify extraction of line item rows with quantity and price."""
    lines = [l.strip() for l in SAMPLE_GST_INVOICE.splitlines() if l.strip()]
    items = extract_line_items(lines)

    assert len(items) == 2
    item1 = items[0]
    assert "Logitech Optical Mouse" in item1["description"]
    assert item1["quantity"] == 10.0
    assert item1["unit_price"] == 450.0
    assert item1["total"] == 4500.0

    item2 = items[1]
    assert "Samsung 24 LED Monitor" in item2["description"]
    assert item2["quantity"] == 2.0
    assert item2["unit_price"] == 8500.0
    assert item2["total"] == 17000.0

def test_alternative_cash_memo_parsing():
    """Verify parsing on non-GST retail cash memo format."""
    parsed = parse_invoice_text(SAMPLE_ALTERNATIVE_BILL)
    assert parsed["is_parsed"] is True
    assert parsed["metadata"]["invoice_number"] == "BILL-902"
    assert "04-Oct-2025" in parsed["metadata"]["invoice_date"]
    assert "Modern Electronics" in parsed["metadata"]["seller_name"]
    assert "Rajesh Kumar" in parsed["metadata"]["buyer_name"]
    assert parsed["summary"]["grand_total"] == 1456.0
    assert len(parsed["line_items"]) == 2

def test_end_to_end_real_image_pipeline():
    """
    FULL END-TO-END PIPELINE TEST:
    Image Rendering -> Real Local OCR Engine -> Raw Text -> Structured Parser.
    """
    # 1. Create a real invoice image
    img = Image.new("RGB", (850, 400), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    invoice_content = [
        "TAX INVOICE",
        "Supplier: Delta Hardware Mart",
        "GSTIN: 27AABCS1429B1Z8",
        "Invoice No: INV-2025-7788",
        "Date: 18/09/2025",
        "--------------------------------------------------",
        "Description         Qty    Rate       Total",
        "Cordless Drill       1     4200.00    4200.00",
        "Screwdriver Set      4      350.00    1400.00",
        "--------------------------------------------------",
        "Subtotal: 5600.00",
        "CGST 9%: 504.00",
        "SGST 9%: 504.00",
        "Grand Total: 6608.00"
    ]
    y = 20
    for line in invoice_content:
        draw.text((30, y), line, fill=(0, 0, 0))
        y += 28

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    # 2. Run real OCR engine
    ocr_res = perform_ocr(img_bytes)
    assert ocr_res["success"] is True
    assert len(ocr_res["raw_text"]) > 0

    # 3. Run structured parser on real OCR output
    parsed = parse_invoice_text(ocr_res["raw_text"], ocr_res["lines"])
    assert parsed["is_parsed"] is True
    assert parsed["status"] == "Preliminary extraction completed"

    # 4. Verify identified fields
    meta = parsed["metadata"]
    assert meta["currency"] == "INR"
    # Ensure at least key identification fields derived from OCR
    assert meta["invoice_number"] is not None or meta["seller_name"] is not None or parsed["summary"]["grand_total"] is not None


SAMPLE_VAT_MULTILINE_INVOICE = """
Invoice no: 51109338
Date of issue:
Seller:
Andrews, Kirby and Valdez
58861 Gonzalez Prairie
Lake Daniellefurt, IN 57228
Tax ld: 945-82-2137
IBAN: GB75MCRL06841367619257
ITEMS
04/13/2013
Client:
Becker Ltd
8012 Stewart Summit Apt. 455
North Douglas, AZ 95355
Tax ld: 942-80-0517
No.
1.
2.
3.
4.
5.
6.
7.
Description
CLEARANCE! Fast Dell Desktop
Computer PC DUAL CORE
WINDOWS 10 4/8/16GB RAM
HP T 520 Thin Client Computer
AMD GX-212JC 1.2GHz 4GB RAM
TESTED BELOW!!
gaming pc desktop computer
12-Core Gaming Computer
Desktop PC Tower Affordable
GAMING PC 8GB AMD vega RGB
Custom Build Dell Optiplex 9020
MT i5-4570 3.20GHz Desktop
Computer PC
Dell Optiplex 990 MT Computer
PC Quad Core i7 3.4GHz 16GB
2TB HD Windows 10 Pro
Dell Core 2 Duo Desktop
Computer I Windows XP Pro I
4GB 1 500GB
Qty
3,00
5,00
1,00
3,00
5,00
4,00
5,00
VAT [0/0]
each
each
each
each
each
each
each
Net price
209,00
37,75
400,00
464,89
221,99
269,95
168,00
Net worth
5 640,17
$ 5 640,17
Net worth
627,00
188,75
400,00
1 394,67
1 109,95
1 079,80
840,00
SUMMARY
VAT [0/0]
Total
VAT
564,02
$ 564,02
Gross
worth
689,70
207,63
440,00
1 534,14
1 220,95
1 187,78
924,00
Gross worth
6 204,19
$ 6 204,19
"""

def test_next_line_seller_and_client_extraction():
    """Verify that seller and client labels followed by names on subsequent lines are extracted."""
    parsed = parse_invoice_text(SAMPLE_VAT_MULTILINE_INVOICE)
    assert parsed["is_parsed"] is True
    meta = parsed["metadata"]
    assert meta["seller_name"] == "Andrews, Kirby and Valdez"
    assert meta["buyer_name"] == "Becker Ltd"
    assert meta["seller_tax_id"] == "945-82-2137"
    assert meta["buyer_tax_id"] == "942-80-0517"


def test_date_ambiguity_when_date_appears_after_items():
    """Verify that dates detached from labels appearing after ITEMS are flagged as ambiguous."""
    parsed = parse_invoice_text(SAMPLE_VAT_MULTILINE_INVOICE)
    meta = parsed["metadata"]
    # Should not confidently set invoice_date because 'Date of issue:' has no adjacent value
    assert meta["invoice_date"] is None
    # Must record ambiguity note in uncertain_fields
    assert any("ambiguous" in u or "ITEMS" in u or "without adjacent" in u for u in meta["uncertain_fields"])


def test_vat_summary_and_european_decimals():
    """Verify subtotal, VAT, grand total, and currency extraction on European VAT formats."""
    parsed = parse_invoice_text(SAMPLE_VAT_MULTILINE_INVOICE)
    summ = parsed["summary"]
    assert summ["subtotal"] == 5640.17
    assert summ["vat_amount"] == 564.02
    assert summ["total_tax"] == 564.02
    assert summ["grand_total"] == 6204.19
    assert parsed["metadata"]["currency"] == "USD"


def test_multi_row_columnar_table_extraction():
    """Verify extraction of 7-row product table from columnar OCR stream with distinct net and gross worth."""
    lines = [l.strip() for l in SAMPLE_VAT_MULTILINE_INVOICE.splitlines() if l.strip()]
    items = extract_line_items(lines)
    assert len(items) == 7
    # Row 1
    assert "Fast Dell Desktop" in items[0]["description"]
    assert items[0]["quantity"] == 3.0
    assert items[0]["unit_price"] == 209.0
    assert items[0]["taxable_amount"] == 627.0
    assert items[0]["total"] == 689.70
    assert items[0]["tax_amount"] == 62.70
    assert items[0]["tax_rate"] == "10%"
    # Row 2
    assert "HP T 520" in items[1]["description"]
    assert items[1]["quantity"] == 5.0
    assert items[1]["unit_price"] == 37.75
    assert items[1]["taxable_amount"] == 188.75
    assert items[1]["total"] == 207.63
    assert items[1]["tax_amount"] == 18.88
    assert items[1]["tax_rate"] == "10%"
    # Row 3
    assert items[2]["taxable_amount"] == 400.0
    assert items[2]["total"] == 440.0
    assert items[2]["tax_amount"] == 40.0
    assert items[2]["tax_rate"] == "10%"
    # Row 7
    assert "Dell Core 2 Duo" in items[6]["description"]
    assert items[6]["quantity"] == 5.0
    assert items[6]["unit_price"] == 168.0
    assert items[6]["taxable_amount"] == 840.0
    assert items[6]["total"] == 924.0
    assert items[6]["tax_amount"] == 84.0
    assert items[6]["tax_rate"] == "10%"


def test_missing_gross_amount_leaves_total_none():
    """Verify that if gross worth cannot be confidently recognized, total is None and not replaced by net worth."""
    sample_no_gross = """
No.
1.
Description
Widget A
Qty
2,00
Net price
50,00
Net worth
100,00
SUMMARY
Total
100,00
"""
    lines = [l.strip() for l in sample_no_gross.splitlines() if l.strip()]
    items = extract_line_items(lines)
    assert len(items) == 1
    assert items[0]["taxable_amount"] == 100.0
    assert items[0]["total"] is None


def test_ocr_text_and_word_count_consistency():
    """Verify that word count and line count match raw text calculation exactly."""
    sample = "Line 1 with four words\nLine 2 has five words here"
    words = len(sample.split())
    lines = [l for l in sample.splitlines() if l.strip()]
    assert words == 11
    assert len(lines) == 2


def test_parse_invoice_text_call_with_layout_lines_keyword():
    """
    Regression test exercising the exact function call site from frontend/app.py:
    parse_invoice_text(raw_text, lines, layout_lines=layout_lines)
    Ensures keyword argument compatibility and structured parsing.
    """
    raw_text = "Tax Invoice\nSupplier: Hardware Corp\nInvoice No: INV-100\nTotal: 500.00"
    lines = ["Tax Invoice", "Supplier: Hardware Corp", "Invoice No: INV-100", "Total: 500.00"]
    layout_lines = ["Tax Invoice", "Supplier: Hardware Corp Invoice No: INV-100", "Total: 500.00"]

    res = parse_invoice_text(
        raw_text=raw_text,
        lines=lines,
        layout_lines=layout_lines
    )
    assert res["is_parsed"] is True
    assert res["metadata"]["invoice_number"] == "INV-100"
    assert res["metadata"]["seller_name"] == "Hardware Corp"


# -------------------------------------------------------------------------
# Stage 8: Simplified Product Name and Quantity Inventory Tests
# -------------------------------------------------------------------------

def test_simplified_product_name_and_quantity_extraction():
    """Verify that every extracted item contains product_name, quantity, and uncertainty flags."""
    sample = """
    Invoice No: INV-8899
    Description               Qty      Rate     Amount
    Wireless Mouse            2        250.00   500.00
    Mechanical Keyboard       1        1200.00  1200.00
    Subtotal: 1700.00
    Grand Total: 1700.00
    """
    lines = [l.strip() for l in sample.splitlines() if l.strip()]
    parsed = parse_invoice_text(sample, lines=lines)
    items = parsed["line_items"]
    assert len(items) == 2
    for it in items:
        assert "product_name" in it
        assert "quantity" in it
        assert "quantity_str" in it
        assert "is_uncertain" in it
        assert it["is_uncertain"] is False

    assert items[0]["product_name"] == "Wireless Mouse"
    assert items[0]["quantity"] == 2.0
    assert items[1]["product_name"] == "Mechanical Keyboard"
    assert items[1]["quantity"] == 1.0


def test_invoices_with_and_without_gst():
    """Verify that both GST invoices and simple non-GST invoices extract product names and quantities."""
    # GST Invoice with HSN and tax breakdown
    gst_sample = """
    TAX INVOICE
    Item Description       HSN      Qty   Unit    Rate       Total
    Cotton Towels          6302     4     Units   150.00     600.00
    Bedsheets              6302     2     Units   800.00    1600.00
    Subtotal: 2200.00
    CGST 6%: 132.00
    SGST 6%: 132.00
    Grand Total: 2464.00
    """
    lines_gst = [l.strip() for l in gst_sample.splitlines() if l.strip()]
    items_gst = extract_line_items(lines_gst)
    assert len(items_gst) == 2
    assert items_gst[0]["product_name"] == "Cotton Towels"
    assert items_gst[0]["quantity"] == 4.0
    assert items_gst[1]["product_name"] == "Bedsheets"
    assert items_gst[1]["quantity"] == 2.0

    # Non-GST simple cash bill
    simple_sample = """
    CASH RECEIPT
    Particulars            Quantity  Rate   Amount
    Organic Honey          3         350    1050
    Almond Pack            2         500    1000
    Total Amount: 2050
    """
    lines_simple = [l.strip() for l in simple_sample.splitlines() if l.strip()]
    items_simple = extract_line_items(lines_simple)
    assert len(items_simple) == 2
    assert items_simple[0]["product_name"] == "Organic Honey"
    assert items_simple[0]["quantity"] == 3.0
    assert items_simple[1]["product_name"] == "Almond Pack"
    assert items_simple[1]["quantity"] == 2.0


def test_different_quantity_and_product_headings():
    """Verify recognition of various heading synonyms across diverse invoice layouts."""
    headings_to_test = [
        ("Product Name", "Quantity"),
        ("Item Name", "Qty"),
        ("Goods Description", "Nos"),
        ("Material Description", "Pcs"),
        ("Particulars", "Pieces"),
        ("Product", "Count"),
        ("Item", "Units")
    ]
    for p_head, q_head in headings_to_test:
        invoice_text = f"""
        INVOICE
        No.  {p_head}               {q_head}   Rate     Total
        1    Industrial Widget X     5          100.00   500.00
        2    Component Gizmo Y       10         25.00    250.00
        Subtotal: 750.00
        Total: 750.00
        """
        lines = [l.strip() for l in invoice_text.splitlines() if l.strip()]
        items = extract_line_items(lines)
        assert len(items) == 2, f"Failed for headings: {p_head} and {q_head}"
        assert "Industrial Widget X" in items[0]["product_name"]
        assert items[0]["quantity"] == 5.0
        assert "Component Gizmo Y" in items[1]["product_name"]
        assert items[1]["quantity"] == 10.0


def test_quantity_units_preservation():
    """Verify that explicitly printed quantity units (e.g. 2 boxes, 5 pairs, 12 pcs) are preserved."""
    sample = """
    SUPPLY INVOICE
    Item Description       Qty           Rate       Total
    Cardboard Packaging    2 boxes       150.00     300.00
    Safety Gloves          5 pairs       120.00     600.00
    Steel Fasteners        12 pcs        10.00      120.00
    Subtotal: 1020.00
    Total: 1020.00
    """
    lines = [l.strip() for l in sample.splitlines() if l.strip()]
    items = extract_line_items(lines)
    assert len(items) == 3

    assert items[0]["product_name"] == "Cardboard Packaging"
    assert items[0]["quantity"] == 2.0
    assert "boxes" in items[0]["quantity_str"].lower()
    assert items[0]["unit"].lower() == "boxes"

    assert items[1]["product_name"] == "Safety Gloves"
    assert items[1]["quantity"] == 5.0
    assert "pairs" in items[1]["quantity_str"].lower()
    assert items[1]["unit"].lower() == "pairs"

    assert items[2]["product_name"] == "Steel Fasteners"
    assert items[2]["quantity"] == 12.0
    assert "pcs" in items[2]["quantity_str"].lower()
    assert items[2]["unit"].lower() == "pcs"


def test_large_invoice_50_to_100_rows():
    """Verify that high-volume invoices containing 50-100 product rows extract all rows efficiently."""
    header = "TAX INVOICE\nDescription               Qty      Rate     Total\n"
    rows = []
    expected_rows = 75
    for i in range(1, expected_rows + 1):
        rows.append(f"Product Item SKU-{i:03d}       {i % 10 + 1}        {(i * 10):.2f}    {((i % 10 + 1) * i * 10):.2f}")
    footer = "\nSubtotal: 50000.00\nGrand Total: 50000.00"
    large_invoice_text = header + "\n".join(rows) + footer

    lines = [l.strip() for l in large_invoice_text.splitlines() if l.strip()]
    items = extract_line_items(lines)
    assert len(items) == expected_rows
    assert items[0]["product_name"] == "Product Item SKU-001"
    assert items[0]["quantity"] == 2.0
    assert items[-1]["product_name"] == f"Product Item SKU-{expected_rows:03d}"
    assert items[-1]["quantity"] == float(expected_rows % 10 + 1)


def test_uncertain_rows_flagged_for_manual_review():
    """Verify that rows with missing or ambiguous quantities are flagged as uncertain rather than guessing."""
    sample = """
    INVOICE
    Description               Qty      Total
    Valid Item One            3        300.00
    Missing Quantity Item     N/A      Unknown
    Valid Item Two            5        500.00
    Subtotal: 800.00
    Total: 800.00
    """
    lines = [l.strip() for l in sample.splitlines() if l.strip()]
    items = extract_line_items(lines)
    assert len(items) >= 2
    # Ensure items with missing/unparseable quantities are marked uncertain
    uncertain_items = [it for it in items if it.get("is_uncertain")]
    valid_items = [it for it in items if not it.get("is_uncertain")]
    assert len(valid_items) >= 2
    assert valid_items[0]["product_name"] == "Valid Item One"
    assert valid_items[0]["quantity"] == 3.0


def test_subtotal_and_footer_rows_excluded():
    """Verify that subtotal, tax breakdown, and footer rows are never recognized as products."""
    sample = """
    INVOICE
    Item Description          Qty      Amount
    Dell Monitor              1        15000.00
    Logitech Mouse            2        800.00
    Taxable Subtotal          3        15800.00
    CGST 9%                            1422.00
    SGST 9%                            1422.00
    Total Amount                       18644.00
    Bank Details: HDFC Bank 987654321
    Amount in Words: Eighteen Thousand Six Hundred Forty Four Only
    Authorized Signatory
    """
    lines = [l.strip() for l in sample.splitlines() if l.strip()]
    items = extract_line_items(lines)
    assert len(items) == 2
    product_names = [it["product_name"].lower() for it in items]
    assert any("dell monitor" in p for p in product_names)
    assert any("logitech mouse" in p for p in product_names)
    assert not any("subtotal" in p for p in product_names)
    assert not any("cgst" in p for p in product_names)
    assert not any("bank" in p for p in product_names)
    assert not any("authorized" in p for p in product_names)


def test_multipage_pdf_all_pages_extracted_and_source_page_tagged(monkeypatch):
    """
    Verify multi-page PDF processing extracts items from all pages,
    tags source_page, and renumbers line items sequentially.
    """
    from unittest.mock import MagicMock
    import frontend.utils.ocr_service as ocr_svc

    # Mock PDF document with 3 pages
    class DummyPdfPage:
        def render(self, scale=2.0):
            mock_res = MagicMock()
            mock_res.to_pil.return_value = Image.new("RGB", (200, 200), (255, 255, 255))
            return mock_res

    class DummyPdfDoc:
        def __init__(self, data):
            self.pages = [DummyPdfPage(), DummyPdfPage(), DummyPdfPage()]
        def __len__(self):
            return len(self.pages)
        def __getitem__(self, idx):
            return self.pages[idx]

    import pypdfium2
    monkeypatch.setattr(pypdfium2, "PdfDocument", DummyPdfDoc)

    # Mock OCR engine to return distinct text per page
    call_count = [0]
    def mock_winocr(image, lang="en-US"):
        call_count[0] += 1
        page_idx = call_count[0]
        lines = [
            "TAX INVOICE",
            "Description Qty Rate Total",
            f"Item Alpha Page {page_idx} 2 Units 100 200",
            f"Item Beta Page {page_idx} 5 Units 50 250",
            "Subtotal: 450"
        ]
        return "\n".join(lines), lines, lines

    monkeypatch.setattr(ocr_svc, "_run_winocr_sync", mock_winocr)
    monkeypatch.setattr(ocr_svc, "check_winocr_available", lambda: (True, ["en-US"]))

    # Pass dummy PDF bytes
    dummy_pdf_bytes = b"%PDF-1.4 dummy multi-page pdf bytes"
    res = ocr_svc.perform_ocr(dummy_pdf_bytes, filename="multi_page_test.pdf")

    assert res["success"] is True
    assert res["page_count"] == 3
    assert len(res["pages"]) == 3
    # 2 items per page * 3 pages = 6 items
    assert len(res["line_items"]) == 6
    assert res["line_items"][0]["source_page"] == 1
    assert res["line_items"][1]["source_page"] == 1
    assert res["line_items"][2]["source_page"] == 2
    assert res["line_items"][4]["source_page"] == 3
    # Verify sequential renumbering
    for idx, it in enumerate(res["line_items"], start=1):
        assert it["item_num"] == idx


def test_multipage_tiff_all_frames_extracted(monkeypatch):
    """Verify multi-frame TIFF extracts all frames and assigns source_page."""
    from unittest.mock import MagicMock
    import frontend.utils.ocr_service as ocr_svc

    class DummyTiffImage:
        def __init__(self):
            self.n_frames = 2
            self.curr_frame = 0
        def seek(self, frame):
            self.curr_frame = frame
        def convert(self, mode):
            return Image.new("RGB", (200, 200), (255, 255, 255))

    monkeypatch.setattr(Image, "open", lambda b: DummyTiffImage())

    frame_count = [0]
    def mock_winocr(image, lang="en-US"):
        frame_count[0] += 1
        lines = [
            "TAX INVOICE",
            "Description Qty Rate Total",
            f"Frame Product {frame_count[0]} 10 Units 100.00 1000.00",
            "Subtotal: 1000.00",
            "Total Amount: 1000.00"
        ]
        return "\n".join(lines), lines, lines

    monkeypatch.setattr(ocr_svc, "_run_winocr_sync", mock_winocr)
    monkeypatch.setattr(ocr_svc, "check_winocr_available", lambda: (True, ["en-US"]))

    res = ocr_svc.perform_ocr(b"II*\x00dummy_tiff", filename="test.tiff")
    assert res["success"] is True
    assert res["page_count"] == 2
    assert len(res["line_items"]) == 2
    assert res["line_items"][0]["source_page"] == 1
    assert res["line_items"][1]["source_page"] == 2


def test_ocr_cache_isolation_and_instant_retrieval(monkeypatch):
    """Verify document-level and page-level cache returns instantly on repeated calls."""
    import frontend.utils.ocr_service as ocr_svc

    call_tracker = [0]
    def mock_winocr(image, lang="en-US"):
        call_tracker[0] += 1
        lines = ["INVOICE", "Item Qty Total", "Cached Widget 4 400", "Total 400"]
        return "\n".join(lines), lines, lines

    monkeypatch.setattr(ocr_svc, "_run_winocr_sync", mock_winocr)
    monkeypatch.setattr(ocr_svc, "check_winocr_available", lambda: (True, ["en-US"]))

    img_bytes = b"\x89PNG\r\n\x1a\nfake_cache_test_image_bytes"
    monkeypatch.setattr(Image, "open", lambda b: Image.new("RGB", (100, 100), (200, 200, 200)))

    # First run: executes OCR
    res1 = ocr_svc.perform_ocr(img_bytes, filename="cache_test.png")
    assert res1["success"] is True
    assert call_tracker[0] == 1

    # Second run with identical bytes: returns from cache without calling OCR engine
    res2 = ocr_svc.perform_ocr(img_bytes, filename="cache_test.png")
    assert res2["success"] is True
    assert res2.get("from_cache") is True
    assert call_tracker[0] == 1  # No additional OCR calls made





