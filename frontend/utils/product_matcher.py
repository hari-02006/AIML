"""
Product Matcher Utility for Stage 9.
Provides exact and normalized product matching against the PostgreSQL products catalog,
canonical unit matching, conversion factor validation, and ambiguous candidate detection.
"""

import re
from typing import Dict, Any, List, Optional, Tuple


def normalize_string(s: Optional[str]) -> str:
    """Normalizes whitespace, casing, and punctuation for safe comparison."""
    if not s:
        return ""
    # Lowercase, remove special characters except alphanumeric and single spaces
    clean = re.sub(r"[^\w\s]", " ", s.lower())
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def normalize_unit(unit_str: Optional[str]) -> str:
    """Normalizes common unit variations to a canonical string."""
    if not unit_str:
        return ""
    u = unit_str.strip().lower()
    mapping = {
        "box": "boxes",
        "boxes": "boxes",
        "pair": "pairs",
        "pairs": "pairs",
        "piece": "pieces",
        "pieces": "pieces",
        "pc": "pieces",
        "pcs": "pieces",
        "pack": "packs",
        "packs": "packs",
        "pkt": "packs",
        "pkts": "packs",
        "unit": "units",
        "units": "units",
        "set": "sets",
        "sets": "sets",
        "nos": "units",
        "each": "units",
    }
    return mapping.get(u, u)


def match_product_against_catalog(
    ocr_name: Optional[str],
    catalog: List[Dict[str, Any]],
    threshold_similarity: float = 0.8
) -> Dict[str, Any]:
    """
    Matches an extracted OCR product name against the product catalog.
    Returns:
      {
        "status": "exact_match" | "normalized_match" | "ambiguous" | "unmatched",
        "matched_product": Optional[Dict],
        "candidates": List[Dict],
        "match_confidence": float
      }
    """
    if not ocr_name or not ocr_name.strip():
        return {
            "status": "unmatched",
            "matched_product": None,
            "candidates": [],
            "match_confidence": 0.0
        }

    raw_clean = ocr_name.strip()
    norm_query = normalize_string(raw_clean)

    # 1. Exact Name Match (case-sensitive or exact string)
    for prod in catalog:
        if prod["product_name"] == raw_clean:
            return {
                "status": "exact_match",
                "matched_product": prod,
                "candidates": [prod],
                "match_confidence": 1.0
            }

    # 2. Normalized Exact Match
    normalized_matches = []
    for prod in catalog:
        if normalize_string(prod["product_name"]) == norm_query:
            normalized_matches.append(prod)

    if len(normalized_matches) == 1:
        return {
            "status": "normalized_match",
            "matched_product": normalized_matches[0],
            "candidates": normalized_matches,
            "match_confidence": 0.95
        }
    elif len(normalized_matches) > 1:
        return {
            "status": "ambiguous",
            "matched_product": None,
            "candidates": normalized_matches,
            "match_confidence": 0.85
        }

    # 3. Substring / Token Overlap Match
    query_tokens = set(norm_query.split())
    candidates = []
    for prod in catalog:
        prod_tokens = set(normalize_string(prod["product_name"]).split())
        if not prod_tokens or not query_tokens:
            continue
        common = query_tokens.intersection(prod_tokens)
        score = len(common) / max(len(query_tokens), len(prod_tokens))
        if score >= 0.5:
            candidates.append((score, prod))

    candidates.sort(key=lambda x: x[0], reverse=True)

    if len(candidates) == 1 and candidates[0][0] >= 0.75:
        return {
            "status": "normalized_match",
            "matched_product": candidates[0][1],
            "candidates": [candidates[0][1]],
            "match_confidence": round(candidates[0][0], 2)
        }
    elif len(candidates) > 1:
        top_candidates = [c[1] for c in candidates if c[0] >= 0.5]
        return {
            "status": "ambiguous",
            "matched_product": None,
            "candidates": top_candidates,
            "match_confidence": round(candidates[0][0], 2)
        }

    return {
        "status": "unmatched",
        "matched_product": None,
        "candidates": [],
        "match_confidence": 0.0
    }


def validate_unit_conversion(
    invoice_unit: Optional[str],
    canonical_stock_unit: Optional[str],
    user_conversion_factor: Optional[float] = None
) -> Tuple[bool, Optional[float], Optional[str]]:
    """
    Validates unit compatibility and computes the conversion factor.
    Returns:
      (is_valid, conversion_factor, error_message_or_info)
    """
    if not canonical_stock_unit or not canonical_stock_unit.strip():
        return False, None, "Product canonical stock unit is missing. Please confirm stock unit first."

    norm_canonical = normalize_unit(canonical_stock_unit)
    norm_invoice = normalize_unit(invoice_unit) if invoice_unit else ""

    # Case 1: Invoice has no unit specified -> must be explicitly confirmed
    if not norm_invoice:
        if user_conversion_factor is not None:
            if user_conversion_factor <= 0:
                return False, None, "Conversion factor must be strictly greater than zero."
            return True, float(user_conversion_factor), f"Confirmed conversion factor: {user_conversion_factor}"
        return False, None, f"Invoice does not specify a unit. Please confirm whether it matches '{canonical_stock_unit}'."

    # Case 2: Matching units
    if norm_invoice == norm_canonical:
        return True, 1.0, f"Units match canonical stock unit '{canonical_stock_unit}' directly."

    # Case 3: Mismatched units -> require explicit positive conversion factor
    if user_conversion_factor is not None:
        if user_conversion_factor <= 0:
            return False, None, "Conversion factor must be strictly greater than zero."
        return True, float(user_conversion_factor), f"1 {invoice_unit} = {user_conversion_factor} {canonical_stock_unit}"

    return False, None, f"Unit Mismatch: Invoice specifies '{invoice_unit}' but stock unit is '{canonical_stock_unit}'. Conversion factor required."
