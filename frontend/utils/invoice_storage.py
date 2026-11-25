"""
Invoice Document Storage Manager for Stage 9.
Coordinates physical file persistence across:
  data/invoices/pending/
  data/invoices/approved/
  data/invoices/rejected/

Implements a safe copy-and-commit protocol:
  1. Files are uploaded into pending/
  2. On approval, file is copied to approved/ and SHA-256 verified
  3. Only after the PostgreSQL transaction commits is the pending file safely removed.
"""

import os
import shutil
import hashlib
from pathlib import Path
from typing import Tuple, Optional


# Base project root directory
BASE_DIR = Path(__file__).resolve().parents[2]
INVOICES_DIR = BASE_DIR / "data" / "invoices"
PENDING_DIR = INVOICES_DIR / "pending"
APPROVED_DIR = INVOICES_DIR / "approved"
REJECTED_DIR = INVOICES_DIR / "rejected"


def ensure_storage_directories():
    """Creates the managed invoice storage folders if they do not exist."""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    APPROVED_DIR.mkdir(parents=True, exist_ok=True)
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)


def compute_bytes_sha256(data: bytes) -> str:
    """Computes SHA-256 hex digest of raw byte content."""
    return hashlib.sha256(data).hexdigest()


def compute_file_sha256(filepath: Path) -> str:
    """Computes SHA-256 hex digest of a file on disk."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def save_pending_invoice_document(data: bytes, original_filename: str) -> Tuple[str, str, str]:
    """
    Saves an uploaded document into data/invoices/pending/.
    Generates a collision-safe filename using a content hash prefix.
    Returns:
      (document_hash, safe_filename, relative_storage_path)
    """
    ensure_storage_directories()
    doc_hash = compute_bytes_sha256(data)
    clean_name = Path(original_filename or "document").name.replace(" ", "_") or "document"
    safe_filename = f"{doc_hash[:16]}_{clean_name}"
    target_path = PENDING_DIR / safe_filename

    # If the file does not already exist, write it
    if not target_path.exists():
        with open(target_path, "wb") as f:
            f.write(data)

    rel_path = str(target_path.relative_to(BASE_DIR)).replace("\\", "/")
    return doc_hash, safe_filename, rel_path


def stage_approved_document(pending_rel_path: str, expected_hash: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Pre-commit step: Copies the file from pending/ to approved/ and verifies SHA-256.
    Returns:
      (success, approved_rel_path, error_message)
    """
    ensure_storage_directories()
    source_path = (BASE_DIR / pending_rel_path).resolve()
    try:
        source_path.relative_to(INVOICES_DIR.resolve())
    except ValueError:
        return False, None, f"Security violation: path traversal detected for {pending_rel_path}"

    if not source_path.exists():
        return False, None, f"Source pending document not found: {pending_rel_path}"

    filename = source_path.name
    approved_target = (APPROVED_DIR / filename).resolve()
    try:
        approved_target.relative_to(APPROVED_DIR.resolve())
    except ValueError:
        return False, None, "Security violation: invalid approved target path"

    try:
        shutil.copy2(source_path, approved_target)
        copied_hash = compute_file_sha256(approved_target)
        if copied_hash != expected_hash:
            # Hash verification failure! Clean up corrupt copy immediately
            if approved_target.exists():
                approved_target.unlink()
            return False, None, f"Hash verification mismatch: expected {expected_hash}, got {copied_hash}"

        rel_path = str(approved_target.relative_to(BASE_DIR)).replace("\\", "/")
        return True, rel_path, None
    except Exception as exc:
        if approved_target.exists():
            try:
                approved_target.unlink()
            except Exception:
                pass
        return False, None, f"Failed to stage approved document: {str(exc)}"


def commit_approved_document(pending_rel_path: str) -> bool:
    """
    Post-commit step: Safely deletes the redundant pending file after successful DB commit.
    """
    source_path = (BASE_DIR / pending_rel_path).resolve()
    try:
        source_path.relative_to(INVOICES_DIR.resolve())
    except ValueError:
        return False
    try:
        if source_path.exists():
            source_path.unlink()
        return True
    except Exception:
        # File removal warning - DB is already committed and safe
        return False


def rollback_staged_approved_document(approved_rel_path: str):
    """
    Rollback step: Removes staged approved document if the DB transaction fails.
    """
    if not approved_rel_path:
        return
    target = (BASE_DIR / approved_rel_path).resolve()
    try:
        target.relative_to(APPROVED_DIR.resolve())
    except ValueError:
        return
    try:
        if target.exists():
            target.unlink()
    except Exception:
        pass


def stage_rejected_document(pending_rel_path: str, expected_hash: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Copies document from pending/ to rejected/ and verifies hash.
    """
    ensure_storage_directories()
    source_path = (BASE_DIR / pending_rel_path).resolve()
    try:
        source_path.relative_to(INVOICES_DIR.resolve())
    except ValueError:
        return False, None, f"Security violation: path traversal detected for {pending_rel_path}"

    if not source_path.exists():
        return False, None, f"Source pending document not found: {pending_rel_path}"

    filename = source_path.name
    rejected_target = (REJECTED_DIR / filename).resolve()
    try:
        rejected_target.relative_to(REJECTED_DIR.resolve())
    except ValueError:
        return False, None, "Security violation: invalid rejected target path"

    try:
        shutil.copy2(source_path, rejected_target)
        copied_hash = compute_file_sha256(rejected_target)
        if copied_hash != expected_hash:
            if rejected_target.exists():
                rejected_target.unlink()
            return False, None, "Hash mismatch on rejection copy"
        rel_path = str(rejected_target.relative_to(BASE_DIR)).replace("\\", "/")
        return True, rel_path, None
    except Exception as exc:
        return False, None, str(exc)
