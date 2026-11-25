"""
OCR Service for Smart Inventory & Demand Prediction System.
Provides a local, privacy-preserving OCR pipeline on Windows.
Supports PaddleOCR-VL 1.6 (Local VLM), Windows Media OCR (built-in Windows 10/11), and Tesseract OCR.
"""

import io
import os
import time
import shutil
import hashlib
import asyncio
import concurrent.futures
from typing import Tuple, Optional, Dict, Any, List
from PIL import Image, ImageOps, ImageEnhance

# In-memory result cache to avoid repeatedly re-processing identical documents:
# Key: (sha256_hash, page_idx, engine_str, parser_version) -> result_dict
_OCR_RESULT_CACHE: Dict[Tuple[str, int, str, str], Dict[str, Any]] = {}
_DOC_RESULT_CACHE: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
PARSER_VERSION = "v2"

# -------------------------------------------------------------------------
# Engine Availability Detection
# -------------------------------------------------------------------------

def check_tesseract_available() -> Tuple[bool, Optional[str]]:
    """Checks whether the Tesseract OCR executable is available."""
    try:
        import pytesseract
        exe = shutil.which("tesseract")
        if exe:
            return True, exe
        # Check standard installation directories on Windows
        standard_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe")
        ]
        for path in standard_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                return True, path
    except Exception:
        pass
    return False, None


def check_winocr_available() -> Tuple[bool, List[str]]:
    """Checks whether Windows Media OCR native runtime is available."""
    try:
        from winrt.windows.media.ocr import OcrEngine
        langs = [l.language_tag for l in OcrEngine.available_recognizer_languages]
        if langs:
            return True, langs
    except Exception:
        pass
    return False, []


def get_available_engines() -> List[str]:
    """Returns a list of local OCR engines detected on this system."""
    engines = []
    try:
        try:
            from frontend.utils.paddleocr_vl_service import is_paddleocr_available
        except ImportError:
            from utils.paddleocr_vl_service import is_paddleocr_available
        if is_paddleocr_available():
            engines.append("PaddleOCR-VL 1.6 (Local VLM)")
    except Exception:
        pass

    win_avail, _ = check_winocr_available()
    if win_avail:
        engines.append("Windows Media OCR (Local)")
    tess_avail, _ = check_tesseract_available()
    if tess_avail:
        engines.append("Tesseract OCR (Local)")
    return engines


def is_ocr_available() -> bool:
    """Returns True if at least one local OCR engine is ready for use."""
    return len(get_available_engines()) > 0


# -------------------------------------------------------------------------
# Image Pre-processing
# -------------------------------------------------------------------------

def preprocess_image_for_ocr(image: Image.Image) -> Image.Image:
    """
    Applies standard contrast enhancement and normalization
    to improve OCR accuracy on photo captures and low-contrast bills.
    Uses adaptive scaling so small, thin characters (like '1') in tables are reliably detected.
    """
    img = image.convert("RGB")
    max_dim = max(img.width, img.height)
    # Upscale low-resolution or thin-line table documents for maximum glyph fidelity
    if max_dim < 1000:
        ratio = max(1000 / img.width, 1000 / img.height)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
    elif max_dim < 3000:
        # Scale up by 1.35x for optimal Windows Media OCR text recognition on fine fonts
        scale = min(1.35, 3500 / max_dim)
        if scale > 1.05:
            new_size = (int(img.width * scale), int(img.height * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
    
    # Mild contrast enhancement
    enhancer = ImageEnhance.Contrast(img)
    img = enhancer.enhance(1.2)
    return img


# -------------------------------------------------------------------------
# Local OCR Execution
# -------------------------------------------------------------------------

def _run_winocr_sync(image: Image.Image, lang: str = "en-US") -> Tuple[str, List[str], List[str]]:
    """
    Runs winocr in a dedicated thread to prevent event-loop conflicts.
    Returns:
      (raw_text, engine_lines, layout_lines)
    where layout_lines groups words by horizontal visual reading order.
    """
    import winocr

    def _worker():
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            res = new_loop.run_until_complete(winocr.recognize_pil(image, lang))
            engine_lines = [line.text.strip() for line in res.lines if line.text.strip()]
            
            # Extract words with bounding boxes for reading-order reconstruction
            words = []
            for line in res.lines:
                for w in line.words:
                    if w.text.strip():
                        words.append({
                            'text': w.text.strip(),
                            'x': float(w.bounding_rect.x),
                            'y': float(w.bounding_rect.y),
                            'w': float(w.bounding_rect.width),
                            'h': float(w.bounding_rect.height)
                        })

            # Cluster words by vertical overlap into horizontal reading lines
            words.sort(key=lambda w: (w['y'], w['x']))
            lines_words = []
            for w in words:
                placed = False
                for lw in lines_words:
                    avg_y = sum(item['y'] for item in lw) / len(lw)
                    avg_h = sum(item['h'] for item in lw) / len(lw)
                    if abs(w['y'] - avg_y) <= avg_h * 0.6:
                        lw.append(w)
                        placed = True
                        break
                if not placed:
                    lines_words.append([w])

            layout_lines = []
            for lw in lines_words:
                lw.sort(key=lambda w: w['x'])
                line_str = " ".join([w['text'] for w in lw]).strip()
                if line_str:
                    layout_lines.append(line_str)

            raw_text = "\n".join(engine_lines)
            return raw_text, engine_lines, layout_lines
        finally:
            new_loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_worker).result()


def _run_tesseract_sync(image: Image.Image) -> Tuple[str, List[str]]:
    """Runs pytesseract image_to_string."""
    import pytesseract
    text = pytesseract.image_to_string(image)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return text.strip(), lines


def perform_ocr(
    image_input: Any,
    preferred_engine: Optional[str] = None,
    filename: Optional[str] = None,
    progress_callback: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Performs fast, privacy-preserving local OCR on a document (single image,
    multi-frame TIFF, or multi-page PDF).
    Processes ALL pages of multi-page documents and extracts line items tagged
    with source_page.
    Defaults to Windows Media OCR for fast, automatic shopkeeper inventory extraction.
    Caches results per-page by (sha256_hash, page_idx, engine, parser_version).
    """
    t_start = time.time()

    if image_input is None:
        return {
            "success": False,
            "engine": None,
            "raw_text": "",
            "lines": [],
            "layout_lines": [],
            "word_count": 0,
            "line_count": 0,
            "page_count": 0,
            "pages": [],
            "line_items": [],
            "processing_time_sec": 0.0,
            "error": "No image input provided."
        }

    # Extract raw bytes if possible for SHA-256 caching and multi-page detection
    raw_bytes = None
    try:
        if isinstance(image_input, bytes):
            raw_bytes = image_input
        elif hasattr(image_input, "getvalue"):
            raw_bytes = image_input.getvalue()
        elif hasattr(image_input, "read"):
            pos = image_input.tell() if hasattr(image_input, "tell") else 0
            raw_bytes = image_input.read()
            if hasattr(image_input, "seek"):
                image_input.seek(pos)
    except Exception:
        raw_bytes = None

    doc_hash = hashlib.sha256(raw_bytes).hexdigest() if raw_bytes else None

    # Check whole document cache first
    doc_cache_key = (doc_hash, str(preferred_engine), PARSER_VERSION) if doc_hash else None
    if doc_cache_key and doc_cache_key in _DOC_RESULT_CACHE:
        cached = dict(_DOC_RESULT_CACHE[doc_cache_key])
        cached["from_cache"] = True
        return cached

    # 1. Try PaddleOCR-VL if explicitly requested
    use_paddleocr = False
    if preferred_engine in ["paddleocr", "PaddleOCR-VL 1.6 (Local VLM)"]:
        use_paddleocr = True

    if use_paddleocr:
        try:
            try:
                from frontend.utils.paddleocr_vl_service import predict_document_paddleocr
            except ImportError:
                from utils.paddleocr_vl_service import predict_document_paddleocr
            paddle_res = predict_document_paddleocr(image_input, filename=filename)
            elapsed = round(time.time() - t_start, 3)
            if paddle_res.get("success"):
                out_res = {
                    "success": True,
                    "engine": "PaddleOCR-VL 1.6 (Local VLM)",
                    "raw_text": paddle_res.get("raw_text", ""),
                    "lines": paddle_res.get("lines", []),
                    "layout_lines": paddle_res.get("layout_lines", []),
                    "word_count": paddle_res.get("total_words", 0),
                    "line_count": paddle_res.get("total_lines", 0),
                    "page_count": paddle_res.get("page_count", 1),
                    "pages": paddle_res.get("pages", []),
                    "markdown": paddle_res.get("markdown", ""),
                    "metadata": paddle_res.get("metadata", {}),
                    "summary": paddle_res.get("summary", {}),
                    "line_items": paddle_res.get("line_items", []),
                    "reconciliation": paddle_res.get("reconciliation", {}),
                    "processing_time_sec": elapsed,
                    "error": None
                }
                if doc_cache_key:
                    _DOC_RESULT_CACHE[doc_cache_key] = out_res
                return out_res
            return {
                "success": False,
                "engine": "PaddleOCR-VL 1.6 (Local VLM)",
                "raw_text": "",
                "lines": [],
                "layout_lines": [],
                "word_count": 0,
                "line_count": 0,
                "page_count": 1,
                "pages": [],
                "markdown": "",
                "metadata": {},
                "summary": {},
                "line_items": [],
                "reconciliation": {},
                "processing_time_sec": elapsed,
                "error": paddle_res.get("error", "PaddleOCR-VL extraction failed.")
            }
        except Exception as exc:
            elapsed = round(time.time() - t_start, 3)
            return {
                "success": False,
                "engine": "PaddleOCR-VL 1.6 (Local VLM)",
                "raw_text": "",
                "lines": [],
                "layout_lines": [],
                "word_count": 0,
                "line_count": 0,
                "page_count": 1,
                "pages": [],
                "markdown": "",
                "metadata": {},
                "summary": {},
                "line_items": [],
                "reconciliation": {},
                "processing_time_sec": elapsed,
                "error": f"PaddleOCR-VL execution error: {str(exc)}"
            }

    # 2. Multi-Page extraction with Windows Media OCR / Tesseract
    # Extract all page images (PDF via pypdfium2, multi-frame TIFF via PIL, or single image)
    page_images: List[Image.Image] = []
    try:
        is_pdf = (raw_bytes and raw_bytes.startswith(b"%PDF")) or (filename and filename.lower().endswith(".pdf"))
        if is_pdf and raw_bytes:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(raw_bytes)
            num_pages = len(pdf)
            for page_idx in range(num_pages):
                page_img = pdf[page_idx].render(scale=2.0).to_pil().convert("RGB")
                page_images.append(page_img)
        elif raw_bytes:
            pil_img = Image.open(io.BytesIO(raw_bytes))
            # Check for multi-frame TIFF
            n_frames = getattr(pil_img, "n_frames", 1)
            if n_frames > 1:
                for frame_idx in range(n_frames):
                    pil_img.seek(frame_idx)
                    page_images.append(pil_img.convert("RGB"))
            else:
                page_images.append(pil_img.convert("RGB"))
        elif isinstance(image_input, Image.Image):
            n_frames = getattr(image_input, "n_frames", 1)
            if n_frames > 1:
                for frame_idx in range(n_frames):
                    image_input.seek(frame_idx)
                    page_images.append(image_input.convert("RGB"))
            else:
                page_images.append(image_input.convert("RGB"))
        else:
            return {
                "success": False,
                "engine": None,
                "raw_text": "",
                "lines": [],
                "word_count": 0,
                "line_count": 0,
                "page_count": 0,
                "pages": [],
                "line_items": [],
                "processing_time_sec": 0.0,
                "error": f"Unsupported image input type: {type(image_input)}"
            }
    except Exception as exc:
        return {
            "success": False,
            "engine": None,
            "raw_text": "",
            "lines": [],
            "word_count": 0,
            "line_count": 0,
            "page_count": 0,
            "pages": [],
            "line_items": [],
            "processing_time_sec": 0.0,
            "error": f"Failed to load image: {str(exc)}"
        }

    total_pages = len(page_images)
    if total_pages == 0:
        return {
            "success": False,
            "engine": None,
            "raw_text": "",
            "lines": [],
            "word_count": 0,
            "line_count": 0,
            "page_count": 0,
            "pages": [],
            "line_items": [],
            "processing_time_sec": 0.0,
            "error": "Document contains no readable pages."
        }

    tess_avail, _ = check_tesseract_available()
    win_avail, win_langs = check_winocr_available()

    if not tess_avail and not win_avail:
        return {
            "success": False,
            "engine": None,
            "raw_text": "",
            "lines": [],
            "word_count": 0,
            "line_count": 0,
            "page_count": total_pages,
            "pages": [],
            "line_items": [],
            "processing_time_sec": 0.0,
            "error": "No supported local OCR engine found. Windows Media OCR or Tesseract is required."
        }

    # Process all pages
    all_pages_data = []
    combined_raw_texts = []
    combined_lines = []
    combined_layout_lines = []
    combined_line_items = []
    engine_name_used = ""

    try:
        from frontend.utils.invoice_parser import parse_invoice_text
    except ImportError:
        from utils.invoice_parser import parse_invoice_text

    for page_idx, page_img in enumerate(page_images):
        page_num = page_idx + 1
        if progress_callback:
            try:
                progress_callback(page_num, total_pages, f"Processing page {page_num} of {total_pages}...")
            except Exception:
                pass

        # Per-page cache lookup
        page_cache_key = (doc_hash, page_idx, str(preferred_engine), PARSER_VERSION) if doc_hash else None
        if page_cache_key and page_cache_key in _OCR_RESULT_CACHE:
            page_dict = dict(_OCR_RESULT_CACHE[page_cache_key])
            all_pages_data.append(page_dict)
            combined_raw_texts.append(page_dict.get("raw_text", ""))
            combined_lines.extend(page_dict.get("lines", []))
            combined_layout_lines.extend(page_dict.get("layout_lines", []))
            combined_line_items.extend(page_dict.get("line_items", []))
            engine_name_used = page_dict.get("engine", engine_name_used)
            continue

        preprocessed_img = preprocess_image_for_ocr(page_img)
        p_raw = ""
        p_lines = []
        p_layout = []

        try:
            if preferred_engine in ["tesseract", "Tesseract OCR (Local)"] and tess_avail:
                p_raw, p_lines = _run_tesseract_sync(preprocessed_img)
                p_layout = list(p_lines)
                engine_name_used = "Tesseract OCR"
            elif win_avail:
                target_lang = "en-US" if "en-US" in win_langs else win_langs[0]
                p_raw, p_lines, p_layout = _run_winocr_sync(preprocessed_img, lang=target_lang)
                engine_name_used = f"Windows Media OCR ({target_lang})"
            elif tess_avail:
                p_raw, p_lines = _run_tesseract_sync(preprocessed_img)
                p_layout = list(p_lines)
                engine_name_used = "Tesseract OCR"

            # Parse line items for this specific page
            page_parsed = parse_invoice_text(p_raw, lines=p_lines, layout_lines=p_layout)
            page_items = page_parsed.get("line_items", [])
            for item in page_items:
                item["source_page"] = page_num
                if "verification_status" not in item:
                    item["verification_status"] = "Needs Review"

            page_dict = {
                "page_num": page_num,
                "engine": engine_name_used,
                "raw_text": p_raw,
                "lines": p_lines,
                "layout_lines": p_layout,
                "word_count": len(p_raw.split()),
                "line_count": len(p_lines),
                "line_items": page_items
            }

            if page_cache_key:
                _OCR_RESULT_CACHE[page_cache_key] = page_dict

            all_pages_data.append(page_dict)
            combined_raw_texts.append(p_raw)
            combined_lines.extend(p_lines)
            combined_layout_lines.extend(p_layout)
            combined_line_items.extend(page_items)

        except Exception as exc:
            # Record failed page gracefully
            all_pages_data.append({
                "page_num": page_num,
                "engine": engine_name_used or "Unknown",
                "raw_text": "",
                "lines": [],
                "layout_lines": [],
                "word_count": 0,
                "line_count": 0,
                "line_items": [],
                "error": str(exc)
            })

    # Renumber item_num across the full multi-page document
    for idx, it in enumerate(combined_line_items):
        it["item_num"] = idx + 1

    total_words = sum(p.get("word_count", 0) for p in all_pages_data)
    total_raw_text = "\n\n--- Page Break ---\n\n".join(combined_raw_texts)
    elapsed = round(time.time() - t_start, 3)

    out_res = {
        "success": True,
        "engine": engine_name_used,
        "raw_text": total_raw_text,
        "lines": combined_lines,
        "layout_lines": combined_layout_lines,
        "word_count": total_words,
        "line_count": len(combined_lines),
        "page_count": total_pages,
        "pages": all_pages_data,
        "line_items": combined_line_items,
        "processing_time_sec": elapsed,
        "error": None
    }

    if doc_cache_key:
        _DOC_RESULT_CACHE[doc_cache_key] = out_res

    return out_res
