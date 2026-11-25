"""
Client service bridge for PaddleOCR-VL 1.6.
Connects the main application (.venv) to the isolated PaddleOCR-VL worker (.venv_paddleocr).
Provides automatic daemon management, health checking, and seamless fallback.
"""

import os
import sys
import time
import io
import json
import base64
import subprocess
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, Tuple, List
from PIL import Image

DEFAULT_SERVER_PORT = 8505
SERVER_URL = f"http://127.0.0.1:{DEFAULT_SERVER_PORT}"
STARTUP_TIMEOUT_SECONDS = 45


def get_paddleocr_python_path() -> Optional[str]:
    """Returns the path to Python inside the isolated PaddleOCR environment, preferring GPU if present."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    candidate_paths = [
        os.path.join(root_dir, ".venv_paddleocr_gpu", "Scripts", "python.exe"),
        os.path.join(root_dir, ".venv_paddleocr_gpu", "bin", "python"),
        os.path.join(root_dir, ".venv_paddleocr", "Scripts", "python.exe"),
        os.path.join(root_dir, ".venv_paddleocr", "bin", "python"),
    ]
    for path in candidate_paths:
        if os.path.exists(path):
            return path
    return None


def get_worker_script_path() -> str:
    """Returns the absolute path to paddleocr_vl_worker.py."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "paddleocr_vl_worker.py"))


def is_paddleocr_available() -> bool:
    """Checks whether the PaddleOCR-VL environment and worker script exist."""
    py_path = get_paddleocr_python_path()
    worker_path = get_worker_script_path()
    return bool(py_path and os.path.exists(py_path) and os.path.exists(worker_path))


def check_server_health(port: int = DEFAULT_SERVER_PORT, timeout: float = 2.0) -> Tuple[bool, Dict[str, Any]]:
    """Checks if the PaddleOCR-VL worker HTTP server is running and ready."""
    url = f"http://127.0.0.1:{port}/health"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                body = json.loads(response.read().decode("utf-8"))
                return True, body
    except Exception:
        pass
    return False, {}


def get_paddleocr_device_info(port: int = DEFAULT_SERVER_PORT) -> Dict[str, Any]:
    """Returns runtime and hardware details for the PaddleOCR service."""
    py_path = get_paddleocr_python_path()
    is_gpu_env = bool(py_path and ".venv_paddleocr_gpu" in py_path)
    alive, body = check_server_health(port)
    return {
        "installed": bool(py_path and os.path.exists(py_path)),
        "python_path": py_path,
        "is_gpu_env": is_gpu_env,
        "server_running": alive,
        "cuda_available": body.get("cuda_available", is_gpu_env),
        "device": body.get("device", "gpu:0" if is_gpu_env else "cpu"),
        "device_name": body.get("device_name", "NVIDIA RTX 3050" if is_gpu_env else "CPU"),
        "is_gpu": body.get("is_gpu", is_gpu_env)
    }


def ensure_server_running(port: int = DEFAULT_SERVER_PORT) -> Tuple[bool, str]:
    """
    Verifies that the server is active.
    If not, attempts to spawn it in the background and waits for it to become ready.
    """
    is_alive, _ = check_server_health(port)
    if is_alive:
        return True, "Server already running"

    py_exe = get_paddleocr_python_path()
    worker_script = get_worker_script_path()

    if not py_exe or not os.path.exists(py_exe):
        return False, f"Isolated Python environment not found at {py_exe}"

    # Launch worker server in background
    cmd = [py_exe, worker_script, "--serve", "--port", str(port)]
    try:
        # Spawn detached / background process
        creationflags = 0
        if sys.platform == "win32":
            # CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
            creationflags = 0x00000200 | 0x00000008

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags
        )

        # Wait for the model to load and the server to respond
        start_time = time.time()
        while time.time() - start_time < STARTUP_TIMEOUT_SECONDS:
            time.sleep(1.5)
            healthy, _ = check_server_health(port)
            if healthy:
                return True, f"Server started successfully on port {port} (PID {proc.pid})"

        return False, f"Server launched (PID {proc.pid}) but did not respond within {STARTUP_TIMEOUT_SECONDS}s"

    except Exception as exc:
        return False, f"Failed to start PaddleOCR-VL worker: {str(exc)}"


def predict_document_paddleocr(
    file_input: Any,
    filename: Optional[str] = None,
    port: int = DEFAULT_SERVER_PORT,
    timeout: int = 600
) -> Dict[str, Any]:
    """
    Sends a document to the PaddleOCR-VL server for extraction.
    Automatically starts the server if it is not currently active.
    """
    # 1. Ensure server is active
    server_ready, msg = ensure_server_running(port)
    if not server_ready:
        return {
            "success": False,
            "engine": "PaddleOCR-VL 1.6 (Local VLM)",
            "error": f"PaddleOCR-VL server unavailable: {msg}"
        }

    # 2. Prepare payload
    payload = {}
    if filename:
        payload["filename"] = filename

    if isinstance(file_input, str) and os.path.exists(file_input):
        payload["file_path"] = os.path.abspath(file_input)
    elif isinstance(file_input, bytes):
        payload["file_bytes_base64"] = base64.b64encode(file_input).decode("utf-8")
    elif hasattr(file_input, "read"):
        raw_bytes = file_input.read()
        payload["file_bytes_base64"] = base64.b64encode(raw_bytes).decode("utf-8")
    elif isinstance(file_input, Image.Image):
        buf = io.BytesIO()
        file_input.save(buf, format="PNG")
        payload["file_bytes_base64"] = base64.b64encode(buf.getvalue()).decode("utf-8")
        if not filename:
            payload["filename"] = "image.png"
    else:
        return {
            "success": False,
            "engine": "PaddleOCR-VL 1.6 (Local VLM)",
            "error": f"Unsupported input type for PaddleOCR-VL: {type(file_input)}"
        }

    # 3. Post to /predict
    url = f"http://127.0.0.1:{port}/predict"
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            resp_body = response.read().decode("utf-8")
            result = json.loads(resp_body)
            return result
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8") if e.fp else str(e)
        return {
            "success": False,
            "engine": "PaddleOCR-VL 1.6 (Local VLM)",
            "error": f"Server HTTP error {e.code}: {err_msg}"
        }
    except Exception as e:
        return {
            "success": False,
            "engine": "PaddleOCR-VL 1.6 (Local VLM)",
            "error": f"Failed to communicate with PaddleOCR-VL server: {str(e)}"
        }
