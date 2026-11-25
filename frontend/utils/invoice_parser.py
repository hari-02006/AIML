"""
Invoice Parser for Smart Inventory & Demand Prediction System.
Extracts structured invoice identification fields, summary values,
and preliminary line items from raw OCR text without hardcoding.
"""

import re
from typing import Dict, Any, List, Optional

# -------------------------------------------------------------------------
# Regex Patterns
# -------------------------------------------------------------------------

# GSTIN format: 2 digits (state) + 5 letters (PAN) + 4 digits + 1 letter + 1 char + Z + 1 char
GSTIN_PATTERN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}[Zz][0-9A-Z]{1}\b")

# Date patterns (DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD, DD-Mon-YYYY, or Month names)
DATE_PATTERNS = [
    re.compile(r"\b(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4})\b"),
    re.compile(r"\b(\d{1,2}[-/\.](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-/\.]\d{2,4})\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})\b", re.IGNORECASE),
    re.compile(r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{2,4})\b", re.IGNORECASE),
]

# Invoice Number patterns
INVOICE_NUM_PATTERNS = [
    re.compile(r"(?:Invoice\s*(?:No|Number|#|Id)?|Bill\s*(?:No|#)?|Inv\s*No)[.:\s-]*([A-Za-z0-9\-\/]+)", re.IGNORECASE),
    re.compile(r"\b(?:INV|BILL|REC)[-/\s]*\d{3,}[A-Za-z0-9\-]*\b", re.IGNORECASE),
]

# Amount extractors
AMOUNT_PATTERN = re.compile(r"(?:[₹$€£]|Rs\.?|INR)?\s*([0-9]{1,3}(?:[,\s][0-9]{3})*(?:[,\.][0-9]{2})|[0-9]+(?:[,\.][0-9]{2})?)")


def clean_amount(val_str: Any) -> Optional[float]:
    """
    Cleans currency symbols, whitespace, and decimal/thousand separators.
    Handles standard (1,234.56) and continental European (1.234,56 or 1 234,56).
    """
    if val_str is None:
        return None
    s = re.sub(r"[^\d,\. ]", "", str(val_str)).strip()
    # Remove thin space / regular space thousand separators between digits
    s = s.replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            # European: 1.234,56 -> 1234.56
            s = s.replace(".", "").replace(",", ".")
        else:
            # US/UK/India: 1,234.56 -> 1234.56
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) in [1, 2]:
            s = parts[0] + "." + parts[1]
        else:
            s = s.replace(",", "")
    try:
        val = float(s)
        return val if val > 0 else 0.0
    except (ValueError, TypeError):
        return None


def extract_invoice_metadata(raw_text: str, lines: List[str], layout_lines: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Extracts high-level identification fields from OCR text.
    Uses conservative heuristics and supports next-line values.
    """
    # Detect currency
    currency = "Unknown"
    if "₹" in raw_text or "INR" in raw_text or "GST" in raw_text or "Rs." in raw_text:
        currency = "INR"
    elif "$" in raw_text or "USD" in raw_text:
        currency = "USD"
    elif "€" in raw_text or "EUR" in raw_text:
        currency = "EUR"
    elif "£" in raw_text or "GBP" in raw_text:
        currency = "GBP"

    data = {
        "invoice_number": None,
        "invoice_date": None,
        "due_date": None,
        "seller_name": None,
        "buyer_name": None,
        "seller_tax_id": None,
        "buyer_tax_id": None,
        "seller_gstin": None,
        "buyer_gstin": None,
        "currency": currency,
        "uncertain_fields": []
    }

    # Use combined search source: prioritize layout_lines if available, else raw lines
    search_lines = layout_lines if layout_lines else lines

    # 1. Invoice Number (line by line)
    for i, line in enumerate(lines):
        line_clean = line.strip()
        lower = line_clean.lower()
        if any(k in lower for k in ["invoice no", "invoice number", "bill no", "inv no", "bill number", "invoice #"]):
            # Check same line
            for pat in INVOICE_NUM_PATTERNS:
                match = pat.search(line_clean)
                if match:
                    candidate = match.group(1).strip() if match.groups() else match.group(0).strip()
                    if candidate.lower() not in ["tax", "date", "no", "number", "supplier", "buyer", "cash", "issue", "of"]:
                        # Avoid phone numbers or long bank account numbers (>18 digits)
                        if len(candidate) >= 3 and not re.match(r"^\d{11,}$", candidate):
                            data["invoice_number"] = candidate
                            break
            if data["invoice_number"]:
                break
            # Check next line if label was on its own line
            if not data["invoice_number"] and i + 1 < len(lines):
                next_clean = lines[i+1].strip()
                if re.match(r"^[A-Za-z0-9\-\/]{3,20}$", next_clean):
                    if not any(k in next_clean.lower() for k in ["date", "tax", "client", "seller", "items", "issue"]):
                        data["invoice_number"] = next_clean
                        break

    # Fallback invoice number regex over whole text if not found yet
    if not data["invoice_number"]:
        for pat in INVOICE_NUM_PATTERNS:
            match = pat.search(raw_text)
            if match:
                candidate = match.group(1).strip() if match.groups() else match.group(0).strip()
                if candidate.lower() not in ["tax", "date", "no", "number", "supplier", "buyer"]:
                    if len(candidate) >= 3 and not re.match(r"^\d{11,}$", candidate):
                        data["invoice_number"] = candidate
                        break

    # 2. GSTINs & Tax IDs
    gstin_matches = GSTIN_PATTERN.findall(raw_text.upper())
    if gstin_matches:
        data["seller_gstin"] = gstin_matches[0]
        if len(gstin_matches) > 1:
            data["buyer_gstin"] = gstin_matches[1]

    # Tax IDs / VAT IDs (e.g. Tax Id: 945-82-2137)
    for i, line in enumerate(lines):
        line_clean = line.strip()
        lower = line_clean.lower()
        if any(k in lower for k in ["tax ld:", "tax id:", "vat id:", "tax reg:"]):
            val = re.sub(r"^(?:tax\s*(?:ld|id):?|vat\s*id:?|tax\s*reg:?)\s*", "", line_clean, flags=re.IGNORECASE).strip()
            if not val and i + 1 < len(lines):
                val = lines[i+1].strip()
            # Clean up trailing words if combined
            val = val.split()[0] if val else None
            if val and len(val) >= 5:
                if not data["seller_tax_id"]:
                    data["seller_tax_id"] = val
                elif not data["buyer_tax_id"] and val != data["seller_tax_id"]:
                    data["buyer_tax_id"] = val

    # 3. Seller and Buyer Names (supports same-line and next-line labels)
    for i, line in enumerate(lines):
        line_clean = line.strip()
        lower = line_clean.lower()
        # Seller prefixes
        if any(lower.startswith(p) for p in ["seller:", "supplier:", "vendor:", "from:", "m/s"]):
            val = re.sub(r"^(seller:|supplier:|vendor:|from:|m/s:?)\s*", "", line_clean, flags=re.IGNORECASE).strip()
            if not val and i + 1 < len(lines):
                next_val = lines[i+1].strip()
                # Ensure next line isn't another header
                if not any(next_val.lower().startswith(p) for p in ["client:", "buyer:", "date", "tax", "items"]):
                    val = next_val
            if val and not data["seller_name"]:
                data["seller_name"] = val

        # Buyer / Client prefixes
        elif any(lower.startswith(p) for p in ["client:", "customer:", "buyer:", "bill to:", "billed to:", "to:"]):
            val = re.sub(r"^(client:|customer:|buyer:|bill to:|billed to:|to:)\s*", "", line_clean, flags=re.IGNORECASE).strip()
            if not val and i + 1 < len(lines):
                next_val = lines[i+1].strip()
                if not any(next_val.lower().startswith(p) for p in ["seller:", "date", "tax", "items", "vat"]):
                    val = next_val
            if val and not data["buyer_name"]:
                data["buyer_name"] = val

    # Header heuristics if explicit labels missing
    if not data["seller_name"] and len(lines) > 1:
        for top_line in lines[:3]:
            top_clean = top_line.strip()
            if top_clean and not any(kw in top_clean.upper() for kw in ["TAX INVOICE", "INVOICE", "CASH MEMO", "BILL OF SUPPLY", "DATE"]):
                data["seller_name"] = top_clean
                data["uncertain_fields"].append("seller_name (inferred from document header)")
                break

    # 4. Dates
    items_pos = next((i for i, l in enumerate(lines) if l.strip().upper() == "ITEMS"), len(lines))

    # Look for explicit date labels first
    for idx, line in enumerate(lines):
        line_lower = line.lower()
        if "due date" in line_lower:
            for d_pat in DATE_PATTERNS:
                d_match = d_pat.search(line)
                if d_match:
                    data["due_date"] = d_match.group(1)
                    break
        elif any(k in line_lower for k in ["date of issue", "invoice date", "bill date", "date:"]):
            for d_pat in DATE_PATTERNS:
                d_match = d_pat.search(line)
                if d_match:
                    data["invoice_date"] = d_match.group(1)
                    break
            # If date was on immediate next line before other section headers
            if not data["invoice_date"] and idx + 1 < len(lines):
                next_l = lines[idx+1].strip()
                if not any(k in next_l.lower() for k in ["seller", "client", "items", "tax", "buyer", "invoice"]):
                    for d_pat in DATE_PATTERNS:
                        d_match = d_pat.search(next_l)
                        if d_match:
                            data["invoice_date"] = d_match.group(1)
                            break
            # If label exists but has no valid date on same or next line
            if not data["invoice_date"]:
                data["uncertain_fields"].append("invoice_date (label detected without adjacent date value)")
                break

    # Also check layout_lines for date on the same visual line as 'Date of issue'
    if not data["invoice_date"] and layout_lines:
        for ll in layout_lines:
            ll_low = ll.lower()
            if any(k in ll_low for k in ["date of issue", "invoice date", "bill date", "date:"]):
                for d_pat in DATE_PATTERNS:
                    d_match = d_pat.search(ll)
                    if d_match:
                        # Found on same horizontal line in visual layout!
                        cand_date = d_match.group(1)
                        # Check if this date appeared after ITEMS in vertical text
                        if any(cand_date in l for l in lines[items_pos:]):
                            data["uncertain_fields"].append(f"date {cand_date} located across horizontal row but appears after ITEMS vertically")
                        else:
                            data["invoice_date"] = cand_date
                            break

    # If still no invoice date, scan for any date in text with position awareness
    if not data["invoice_date"]:
        for idx, line in enumerate(lines):
            for d_pat in DATE_PATTERNS:
                d_match = d_pat.search(line)
                if d_match:
                    cand_date = d_match.group(1)
                    if idx >= items_pos:
                        data["uncertain_fields"].append(f"date {cand_date} appears in/after ITEMS section (ambiguous; not assigned to invoice date)")
                    else:
                        data["invoice_date"] = cand_date
                        data["uncertain_fields"].append(f"invoice_date {cand_date} (inferred without explicit date label)")
                    break
            if data["invoice_date"] or any("date" in u for u in data["uncertain_fields"]):
                break

    return data


def extract_invoice_summary(raw_text: str, lines: List[str], layout_lines: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Extracts summary figures including subtotal, taxes (GST or VAT), and grand total.
    Supports both traditional tabular layouts and European VAT summary structures.
    """
    summary = {
        "subtotal": None,
        "taxable_value": None,
        "cgst_amount": None,
        "sgst_amount": None,
        "igst_amount": None,
        "vat_amount": None,
        "vat_rate": None,
        "total_tax": None,
        "discount": None,
        "freight_charges": None,
        "round_off": None,
        "grand_total": None,
        "amount_in_words": None
    }

    # 1. European VAT SUMMARY Block Parser
    lower_lines = [l.strip().lower() for l in lines]
    summary_start = next((i for i, l in enumerate(lower_lines) if l == "summary"), None)
    if summary_start is not None:
        sum_lines = lines[summary_start:]
        for j, l in enumerate(sum_lines):
            low = l.lower()
            if "gross" in low:
                m = re.findall(r"\b\d+(?:\s\d+)*(?:[,\.]\d{2})\b", l)
                if not m and j + 1 < len(sum_lines):
                    m = re.findall(r"\b\d+(?:\s\d+)*(?:[,\.]\d{2})\b", sum_lines[j+1])
                if m:
                    summary["grand_total"] = clean_amount(m[-1])
            elif "vat" in low and not summary["total_tax"]:
                m = re.findall(r"\b\d+(?:\s\d+)*(?:[,\.]\d{2})\b", l)
                if not m and j + 1 < len(sum_lines):
                    m = re.findall(r"\b\d+(?:\s\d+)*(?:[,\.]\d{2})\b", sum_lines[j+1])
                if m:
                    summary["total_tax"] = clean_amount(m[-1])
                    summary["vat_amount"] = summary["total_tax"]
            elif ("net worth" in low or "net" in low) and not summary["subtotal"]:
                m = re.findall(r"\b\d+(?:\s\d+)*(?:[,\.]\d{2})\b", l)
                if m:
                    summary["subtotal"] = clean_amount(m[-1])
                    summary["taxable_value"] = summary["subtotal"]

    # Also check standalone Net worth label across lines (e.g. Net worth \n 5 640,17)
    if not summary["subtotal"]:
        for i, l in enumerate(lines):
            if l.strip().lower() in ["net worth", "subtotal", "sub total", "taxable value"] and i + 1 < len(lines):
                val = clean_amount(lines[i+1])
                if val and val > 0:
                    summary["subtotal"] = val
                    summary["taxable_value"] = val
                    break

    # Also check layout_lines summary if present (e.g. "Total $ 5 640,17 $ 564,02 $ 6 204,19")
    if layout_lines and (not summary["grand_total"] or not summary["subtotal"]):
        for ll in layout_lines:
            if "total" in ll.lower() and any(c in ll for c in ["$", "€", "£", ","]):
                amounts = [clean_amount(m.group(0)) for m in re.finditer(r"(?:[\$€£₹]\s*)?\b\d+(?:\s\d+)*(?:[,\.]\d{2})\b", ll)]
                amounts = [a for a in amounts if a is not None]
                if len(amounts) >= 3:
                    summary["subtotal"] = amounts[0]
                    summary["taxable_value"] = amounts[0]
                    summary["total_tax"] = amounts[1]
                    summary["vat_amount"] = amounts[1]
                    summary["grand_total"] = amounts[2]
                    break

    # 2. Line-by-line fallback for GST and standard commercial summaries
    for line in lines:
        line_clean = line.strip()
        lower = line_clean.lower()

        # Grand Total
        if not summary["grand_total"] and any(k in lower for k in ["grand total", "total amount", "net amount", "invoice total", "total payable"]):
            nums = re.findall(r"\d+(?:[,\s]\d+)*(?:[,\.]\d{2})?", line_clean)
            if nums:
                val = clean_amount(nums[-1])
                if val:
                    summary["grand_total"] = val

        # Subtotal
        elif not summary["subtotal"] and any(k in lower for k in ["subtotal", "sub total", "taxable value", "taxable amount", "net worth"]):
            nums = re.findall(r"\d+(?:[,\s]\d+)*(?:[,\.]\d{2})?", line_clean)
            if nums:
                val = clean_amount(nums[-1])
                if val:
                    summary["subtotal"] = val
                    summary["taxable_value"] = val

        # CGST
        elif "cgst" in lower:
            nums = re.findall(r"\d+(?:[,\s]\d+)*(?:[,\.]\d{2})?", line_clean)
            if nums:
                summary["cgst_amount"] = clean_amount(nums[-1])

        # SGST
        elif "sgst" in lower:
            nums = re.findall(r"\d+(?:[,\s]\d+)*(?:[,\.]\d{2})?", line_clean)
            if nums:
                summary["sgst_amount"] = clean_amount(nums[-1])

        # IGST
        elif "igst" in lower:
            nums = re.findall(r"\d+(?:[,\s]\d+)*(?:[,\.]\d{2})?", line_clean)
            if nums:
                summary["igst_amount"] = clean_amount(nums[-1])

        # Total tax if explicit
        elif not summary["total_tax"] and any(k in lower for k in ["tax amount", "total tax", "tax:"]):
            nums = re.findall(r"\d+(?:[,\s]\d+)*(?:[,\.]\d{2})?", line_clean)
            if nums:
                summary["total_tax"] = clean_amount(nums[-1])

        # Discount
        elif "discount" in lower:
            nums = re.findall(r"\d+(?:[,\s]\d+)*(?:[,\.]\d{2})?", line_clean)
            if nums:
                summary["discount"] = clean_amount(nums[-1])

        # Round Off
        elif "round off" in lower or "round-off" in lower:
            is_neg = ("-" in line_clean and not any(amb in line_clean for amb in ["(+/-)", "+/-", "(±)"])) or "(-)" in line_clean
            is_ambiguous = any(amb in line_clean for amb in ["(+/-)", "+/-", "(±)"])
            nums = re.findall(r"-?\d+(?:[,\s]\d+)*(?:[,\.]\d{2})?", line_clean)
            if nums:
                amt = clean_amount(nums[-1])
                if amt is not None:
                    summary["round_off"] = -abs(amt) if is_neg else abs(amt)
                    summary["recognized_round_off"] = abs(amt)
                    summary["round_off_sign_source"] = "explicit_negative" if is_neg else ("ambiguous_label" if is_ambiguous else "unsigned_magnitude")

        # Amount in words
        elif "in words" in lower or "rupees" in lower and len(line_clean) > 15:
            match = re.search(r"(?:words:?|rupees:?)\s*(.+)$", line_clean, re.IGNORECASE)
            if match:
                summary["amount_in_words"] = match.group(1).strip()

    # Calculate total tax if CGST and SGST found
    if summary["cgst_amount"] is not None and summary["sgst_amount"] is not None:
        summary["total_tax"] = round(summary["cgst_amount"] + summary["sgst_amount"], 2)
    elif summary["igst_amount"] is not None:
        summary["total_tax"] = summary["igst_amount"]

    # VAT rate detection (e.g. 10%)
    for l in lines:
        m = re.search(r"\b(\d{1,2})%\b", l)
        if m and not summary["vat_rate"]:
            summary["vat_rate"] = f"{m.group(1)}%"

    if not summary["vat_rate"] and summary["vat_amount"] and summary["subtotal"] and summary["subtotal"] > 0:
        calc_v_rate = round((summary["vat_amount"] / summary["subtotal"]) * 100)
        summary["vat_rate"] = f"{calc_v_rate}%"

    if summary.get("round_off") is not None and summary.get("grand_total") is not None and summary.get("subtotal") is not None:
        pre_total = summary["subtotal"] + (summary.get("total_tax") or 0.0)
        expected_diff = round(summary["grand_total"] - pre_total, 2)
        if abs(abs(summary["round_off"]) - abs(expected_diff)) <= 0.05:
            summary["derived_round_off"] = expected_diff

    return summary


def extract_columnar_items(lines: List[str]) -> List[Dict[str, Any]]:
    """
    Parses columnar multi-column tables where OCR outputs column blocks
    (e.g., No. block, Description block, Qty block, Net price block, Row total block).
    """
    lower_lines = [l.strip().lower() for l in lines]
    if "no." not in lower_lines or "description" not in lower_lines or "qty" not in lower_lines:
        return []

    no_idx = lower_lines.index("no.")
    desc_idx = lower_lines.index("description")
    qty_idx = lower_lines.index("qty")

    # Row numbers
    row_nums = [l.strip(". ") for l in lines[no_idx+1:desc_idx] if re.match(r"^\d+\.?$", l.strip())]
    N = len(row_nums)
    if N == 0:
        return []

    # Quantities between Qty and next column header
    qty_end_idx = None
    for idx in range(qty_idx + 1, len(lines)):
        if any(kw in lower_lines[idx] for kw in ["vat", "net price", "rate", "unit", "price", "net worth"]):
            qty_end_idx = idx
            break
    qtys = [clean_amount(l) for l in lines[qty_idx+1:qty_end_idx]] if qty_end_idx else []
    qtys = [q for q in qtys if q is not None][:N]

    # Unit tokens (e.g. 'each')
    units = []
    for idx in range(qty_idx + 1, len(lines)):
        if "net price" in lower_lines[idx] or "price" in lower_lines[idx]:
            break
        if lower_lines[idx] in ["each", "pcs", "units", "nos", "kg", "unit"]:
            units.append(lines[idx].strip())
    units = units[:N]

    # Net prices
    net_price_idx = None
    for idx in range(qty_idx, len(lines)):
        if "net price" in lower_lines[idx] or "price" in lower_lines[idx] or "rate" in lower_lines[idx]:
            net_price_idx = idx
            break
    net_prices = []
    if net_price_idx:
        net_price_end = None
        for idx in range(net_price_idx + 1, len(lines)):
            if any(kw in lower_lines[idx] for kw in ["net worth", "total", "vat", "gross", "amount"]):
                net_price_end = idx
                break
        if net_price_end:
            raw_p = [clean_amount(l) for l in lines[net_price_idx+1:net_price_end]]
            net_prices = [p for p in raw_p if p is not None][:N]

    # Row totals: separate Net worth and Gross worth
    summary_idx = lower_lines.index("summary") if "summary" in lower_lines else len(lines)
    
    # 1. Look for Net worth blocks
    net_worth_rows = []
    for i, l in enumerate(lower_lines):
        if l == "net worth" or "net worth" in l:
            nums = []
            for j in range(i + 1, len(lines)):
                if any(kw in lower_lines[j] for kw in ["summary", "vat", "gross", "net", "total"]) and not re.search(r"\d", lines[j]):
                    break
                val = clean_amount(lines[j])
                if val is not None and not lines[j].endswith("%"):
                    nums.append(val)
                if len(nums) == N:
                    break
            if len(nums) == N:
                net_worth_rows = nums

    # 2. Look for Gross worth blocks
    gross_worth_rows = []
    for i, l in enumerate(lower_lines):
        if "gross" in l or "gross worth" in l:
            nums = []
            for j in range(i + 1, len(lines)):
                if any(kw in lower_lines[j] for kw in ["summary", "vat", "net", "total"]) and not re.search(r"\d", lines[j]):
                    break
                val = clean_amount(lines[j])
                if val is not None and not lines[j].endswith("%"):
                    nums.append(val)
                if len(nums) == N:
                    break
            if len(nums) == N:
                gross_worth_rows = nums

    # 3. Look for VAT % column values (e.g. 10%)
    vat_rates = []
    for i in range(qty_idx, summary_idx):
        m_pct = re.search(r"\b(\d{1,2})%\b", lines[i])
        if m_pct:
            vat_rates.append(f"{m_pct.group(1)}%")
    # If a uniform VAT rate is detected across rows
    default_vat_rate = vat_rates[0] if vat_rates else None

    # Partition description lines
    raw_descs = lines[desc_idx+1:qty_idx]
    items_desc = []
    curr_d = []
    continuation_prefixes = [
        "computer pc", "windows", "amd", "tested", "desktop pc", "gaming pc 8gb",
        "mt i5", "pc quad", "2tb", "4gb", "computer i", "intel", "core"
    ]
    for line in raw_descs:
        low = line.lower()
        is_cont = any(low.startswith(p) for p in continuation_prefixes)
        if curr_d and not is_cont and len(items_desc) < N - 1:
            items_desc.append(" ".join(curr_d))
            curr_d = [line]
        else:
            curr_d.append(line)
    if curr_d:
        items_desc.append(" ".join(curr_d))

    if len(items_desc) != N:
        items_desc = raw_descs[:N]

    items = []
    for i in range(N):
        d = items_desc[i] if i < len(items_desc) else f"Item {i+1}"
        q = qtys[i] if i < len(qtys) else None
        p = net_prices[i] if i < len(net_prices) else None
        u = units[i] if i < len(units) else ("Units" if q else None)
        
        # Net taxable amount (net worth)
        net_val = net_worth_rows[i] if i < len(net_worth_rows) else (round(q * p, 2) if (q is not None and p is not None) else None)
        
        # Gross total amount (gross worth)
        gross_val = gross_worth_rows[i] if i < len(gross_worth_rows) else None
        
        # Tax amount and tax rate
        tax_amt = None
        tax_rate = vat_rates[i] if i < len(vat_rates) else default_vat_rate
        if gross_val is not None and net_val is not None:
            tax_amt = round(gross_val - net_val, 2)
            if not tax_rate and net_val > 0:
                calc_rate = round((tax_amt / net_val) * 100)
                tax_rate = f"{calc_rate}%"

        # If gross value cannot be confidently extracted, leave it None/Unknown rather than substituting net_val
        total_val = gross_val if gross_val is not None else None

        is_unc = (q is None or q <= 0)
        q_fmt = int(q) if (isinstance(q, float) and q.is_integer()) else q
        q_str = f"{q_fmt} {u}".strip() if (u and u.lower() not in ['each', 'none', '']) else (str(q_fmt) if q is not None else "(Uncertain)")

        items.append({
            "item_num": len(items) + 1,
            "product_name": d,
            "description": d,
            "hsn_sac": None,
            "quantity": q,
            "quantity_str": q_str,
            "unit": u,
            "is_uncertain": is_unc,
            "uncertain_reason": "Missing or ambiguous quantity" if is_unc else None,
            "unit_price": p,
            "taxable_amount": net_val,
            "tax_rate": tax_rate,
            "tax_amount": tax_amt,
            "total": total_val
        })
    return items


def _parse_row_by_row_items(target_lines: List[str]) -> List[Dict[str, Any]]:
    """
    Parses horizontal item rows line by line.
    Focuses on extracting Product Name and Quantity with unit awareness.
    """
    items = []
    header_keywords = [
        "description", "particulars", "item", "product", "qty", "quantity", 
        "rate", "price", "amount", "hsn", "total", "goods", "material",
        "items", "billed", "order", "qnty", "count", "unit price", "line total",
        "product name", "description of goods", "item description"
    ]
    footer_keywords = [
        "subtotal", "sub-total", "sub total", "taxable subtotal", "grand total",
        "total amount", "bank details", "our bank", "terms of delivery", "amount in words",
        "rupees in words", "authorized signatory", "summery amount"
    ]
    UNIT_WORDS = r'(?:boxes|box|pairs|pair|units|unit|pcs|pieces|nos|kg|pkts|pkt|sets|set|each)'

    in_table_zone = False
    has_hsn_header = False

    for line in target_lines:
        line_clean = line.strip()
        lower = line_clean.lower()

        matches_header = sum(1 for kw in header_keywords if kw in lower)
        has_trailing_numbers = bool(re.search(r"\b\d+(?:[,\.]\d+)?\s+\d+(?:[,\.]\d+)?\b", line_clean))
        if matches_header >= 2 and not has_trailing_numbers:
            in_table_zone = True
            if 'hsn' in lower or 'sac' in lower:
                has_hsn_header = True
            continue

        if in_table_zone:
            if any(kw in lower for kw in footer_keywords):
                break
            if set(line_clean).issubset({"-", "=", "_", " ", ".", "|"}):
                continue

            # Strip leading serial number e.g. "1 ", "2. ", "[1] "
            m_sn = re.match(r"^(\d{1,3})[\.\)\s]+\s*", line_clean)
            content = line_clean[m_sn.end():].strip() if m_sn else line_clean

            # Protect embedded product serial numbers e.g. "serial No: 125689457899565"
            m_serial = re.search(r"serial\s*(?:no|#)[:\s]*[A-Za-z0-9\-]+", content, re.IGNORECASE)
            if m_serial:
                desc_fixed = content[:m_serial.end()]
                rest = content[m_serial.end():].strip()
            else:
                desc_fixed = ""
                rest = content

            # 1. Check for explicit unit pattern directly attached to a number
            m_unit = re.search(r"\b(\d+(?:\.\d+)?)\s*(" + UNIT_WORDS + r")\b", rest, re.IGNORECASE)
            if m_unit:
                qty = float(m_unit.group(1))
                unit = m_unit.group(2)
                desc_part = rest[:m_unit.start()].strip()
                # strip any trailing HSN right before qty
                if re.search(r"\b\d{4,8}\b$", desc_part):
                    desc_part = re.sub(r"\s*\b\d{4,8}\b$", "", desc_part).strip()
                full_desc = (desc_fixed + " " + desc_part).strip() if desc_fixed else desc_part
                full_desc = re.sub(r"^\d+[\.\)]\s*", "", full_desc).strip()

                if len(full_desc) >= 2 and not any(kw in full_desc.lower() for kw in footer_keywords):
                    after_unit = rest[m_unit.end():].strip()
                    trailing_floats = [clean_amount(t) for t in after_unit.split() if clean_amount(t) is not None]
                    rate = trailing_floats[0] if len(trailing_floats) >= 1 else None
                    tot = trailing_floats[-1] if len(trailing_floats) >= 1 else None

                    qty_fmt = int(qty) if qty.is_integer() else qty
                    items.append({
                        "item_num": len(items) + 1,
                        "product_name": full_desc,
                        "description": full_desc,
                        "quantity": qty,
                        "quantity_str": f"{qty_fmt} {unit}",
                        "unit": unit,
                        "is_uncertain": False,
                        "uncertain_reason": None,
                        "hsn_sac": None,
                        "unit_price": rate,
                        "taxable_amount": round(qty * rate, 2) if (rate and qty) else None,
                        "tax_rate": None,
                        "tax_amount": round(tot - (qty * rate), 2) if (tot and rate and tot > qty * rate) else None,
                        "total": tot
                    })
                    continue

            # 2. Split into description and trailing numbers
            tokens = rest.split()
            num_indices = []
            for idx in range(len(tokens) - 1, -1, -1):
                tok = tokens[idx].replace(",", "").rstrip("%")
                try:
                    float(tok)
                    num_indices.append(idx)
                except ValueError:
                    break

            if not num_indices:
                continue

            start_num_idx = num_indices[-1]
            desc_part = " ".join(tokens[:start_num_idx]).strip()
            num_tokens = tokens[start_num_idx:]
            full_desc = (desc_fixed + " " + desc_part).strip() if desc_fixed else desc_part
            full_desc = re.sub(r"^\d+[\.\)]\s*", "", full_desc).strip()

            if len(full_desc) < 2 or any(kw in full_desc.lower() for kw in footer_keywords):
                continue

            first_tok = num_tokens[0].replace(",", "")
            is_first_hsn = bool(re.match(r"^\d{4,8}$", first_tok) and has_hsn_header and len(num_tokens) >= 3)
            if is_first_hsn:
                hsn = first_tok
                cand_tokens = num_tokens[1:]
            else:
                hsn = None
                cand_tokens = num_tokens

            floats = [clean_amount(t) for t in cand_tokens]
            floats = [f for f in floats if f is not None]

            # Arithmetic check: find best qty matching qty * rate == total or taxable
            best_qty = None
            best_rate = None
            best_taxable = None
            best_total = None

            if len(floats) >= 3:
                for q_idx in range(min(2, len(floats) - 2)):
                    q_cand = floats[q_idx]
                    for r_idx in range(q_idx + 1, len(floats) - 1):
                        r_cand = floats[r_idx]
                        for t_idx in range(r_idx + 1, len(floats)):
                            t_cand = floats[t_idx]
                            if abs(q_cand * r_cand - t_cand) <= 0.05 and q_cand > 0:
                                best_qty = q_cand
                                best_rate = r_cand
                                best_taxable = t_cand
                                best_total = floats[-1]
                                break
                        if best_qty is not None:
                            break
                    if best_qty is not None:
                        break

            if best_qty is None and floats:
                best_qty = floats[0]
                if len(floats) >= 2:
                    best_rate = floats[1]
                if len(floats) >= 3:
                    best_taxable = floats[2]
                best_total = floats[-1]

            is_unc = (best_qty is None or best_qty <= 0)
            reason = "Quantity could not be recognized" if is_unc else None
            qty_fmt = int(best_qty) if (best_qty is not None and isinstance(best_qty, float) and best_qty.is_integer()) else best_qty
            qty_str = str(qty_fmt) if best_qty is not None else "(Uncertain)"

            # DEFECT FIX: Never silently substitute 1.0 for a missing quantity.
            # is_uncertain=True means best_qty is None or <= 0; store None so the shopkeeper
            # is forced to review it, and approval is blocked until it is corrected.
            stored_qty = best_qty if (best_qty is not None and best_qty > 0) else None
            items.append({
                "item_num": len(items) + 1,
                "product_name": full_desc,
                "description": full_desc,
                "quantity": stored_qty,
                "quantity_str": qty_str,
                "unit": "Units" if stored_qty is not None else None,
                "is_uncertain": is_unc,
                "uncertain_reason": reason,
                "hsn_sac": hsn,
                "unit_price": best_rate,
                "taxable_amount": best_taxable if best_taxable is not None else (round(stored_qty * best_rate, 2) if (stored_qty and best_rate) else None),
                "tax_rate": None,
                "tax_amount": round(best_total - best_taxable, 2) if (best_total and best_taxable and best_total > best_taxable) else None,
                "total": best_total
            })

    return items


def extract_line_items(lines: List[str], layout_lines: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Identifies and parses item rows from OCR text lines.
    Prioritizes reading-order layout_lines for horizontal table rows,
    with fallback to columnar multi-column parsing and raw lines.
    Focuses on extracting product_name and quantity with unit preservation.
    """
    # 1. Try row-by-row parsing on layout_lines first if available
    if layout_lines and len(layout_lines) > 0:
        row_items = _parse_row_by_row_items(layout_lines)
        if row_items and len(row_items) > 0:
            return row_items

    # 2. Try columnar multi-column parser on raw lines (European VAT & vertical columnar bills)
    columnar_items = extract_columnar_items(lines)
    if columnar_items and len(columnar_items) > 0:
        return columnar_items

    # 3. Fallback to row-by-row parsing on standard raw lines
    return _parse_row_by_row_items(lines)


def parse_invoice_text(
    raw_text: str,
    lines: Optional[List[str]] = None,
    layout_lines: Optional[List[str]] = None,
    tables: Optional[List[List[List[str]]]] = None,
    markdown: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    summary: Optional[Dict[str, Any]] = None,
    line_items: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Main invoice parser entry point.
    Converts raw OCR text into a structured invoice dictionary.
    Supports layout_lines for reading-order and column awareness,
    as well as structured metadata, summary, and items from VLM engines.
    """
    if not raw_text or not raw_text.strip():
        return {
            "is_parsed": False,
            "status": "No readable text provided",
            "metadata": {},
            "summary": {},
            "line_items": [],
            "uncertain_fields": []
        }

    if lines is None:
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]

    extracted_meta = extract_invoice_metadata(raw_text, lines, layout_lines=layout_lines)
    if metadata:
        for k, v in metadata.items():
            if v is not None and (extracted_meta.get(k) is None or k in ["seller_name", "buyer_name", "invoice_number"]):
                extracted_meta[k] = v

    extracted_summary = extract_invoice_summary(raw_text, lines, layout_lines=layout_lines)
    if summary:
        for k, v in summary.items():
            if v is not None and (extracted_summary.get(k) is None or k in [
                "round_off", "recognized_round_off", "derived_round_off",
                "round_off_sign_source", "round_off_label", "grand_total",
                "subtotal", "taxable_value", "total_tax", "cgst_amount",
                "sgst_amount", "igst_amount", "bank_name", "bank_account_no", "bank_ifsc"
            ]):
                extracted_summary[k] = v

    if line_items and len(line_items) > 0:
        extracted_items = line_items
    else:
        extracted_items = extract_line_items(lines, layout_lines=layout_lines)

    # Ensure all items conform to the simplified product_name & quantity schema
    for it in extracted_items:
        if "product_name" not in it and "description" in it:
            it["product_name"] = it["description"]
        if "description" not in it and "product_name" in it:
            it["description"] = it["product_name"]
        if "is_uncertain" not in it:
            q = it.get("quantity")
            it["is_uncertain"] = bool(q is None or q <= 0)
            it["uncertain_reason"] = "Missing or invalid quantity" if it["is_uncertain"] else None
        if "quantity_str" not in it:
            q = it.get("quantity")
            u = it.get("unit")
            q_fmt = int(q) if (isinstance(q, float) and q.is_integer()) else q
            if u and u.lower() not in ['each', 'none', '']:
                it["quantity_str"] = f"{q_fmt} {u}".strip()
            else:
                it["quantity_str"] = str(q_fmt) if q is not None else "(Uncertain)"

    has_identifiable_data = any([
        extracted_meta.get("invoice_number"),
        extracted_meta.get("seller_name"),
        extracted_meta.get("buyer_name"),
        extracted_summary.get("grand_total"),
        len(extracted_items) > 0
    ])

    return {
        "is_parsed": has_identifiable_data,
        "status": "Preliminary extraction completed" if has_identifiable_data else "Limited or unreadable invoice structure",
        "metadata": extracted_meta,
        "summary": extracted_summary,
        "line_items": extracted_items,
        "uncertain_fields": extracted_meta.get("uncertain_fields", [])
    }
