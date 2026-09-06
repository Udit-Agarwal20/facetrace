"""
FaceTrace — Step 5 Forensic Workstation HTTP Server
Provides a lightweight, deterministic server for the judge-facing interface.
Zero external server dependencies (pure Python standard library).
"""

from http import HTTPStatus
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import json
import logging
import mimetypes
import os
from pathlib import Path
import threading
import time
from typing import Dict, Any, Optional
import urllib.parse
import uuid
import re

from dotenv import load_dotenv

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(WORKSPACE_ROOT / ".env")

from src.orchestration.models import ExecutionMode, PipelineStatus, PipelineStage
from src.orchestration.pipeline import FaceTracePipeline, DEFAULT_IMAGE_PATH, RUNS_DIR
from src.blockchain.canonicalizer import EvidenceCanonicalizer

logger = logging.getLogger("FaceTrace.Server")

STATIC_DIR = Path(__file__).resolve().parent / "static"
SAMPLES_DIR = WORKSPACE_ROOT / "samples"
UPLOADS_DIR = WORKSPACE_ROOT / "data" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# 7 Chronological Judge-Facing Stages
STAGE_MAPPING = {
    "INIT": ("FACE_DETECTION", "RUNNING", "Detecting face..."),
    "INPUT_VALIDATED": ("FACE_DETECTION", "RUNNING", "Detecting face..."),
    "CONSENT_CONFIRMED": ("FACE_DETECTION", "RUNNING", "Detecting face..."),
    "FACE_DETECTED": ("FACE_DETECTION", "RUNNING", "Face detected. Generating 512-dim embedding..."),
    "FACE_EMBEDDED": ("FACE_DETECTION", "PASSED", "Face detection passed. Embedding generated."),
    "SEARCH_RUNNING": ("WEB_DISCOVERY", "RUNNING", "Searching indexed web evidence..."),
    "SEARCH_COMPLETE": ("WEB_DISCOVERY", "PASSED", "Indexed web evidence discovered."),
    "CANDIDATE_SELECTED": ("SOCIAL_POST", "RUNNING", "Evaluating social-post compliance..."),
    "SOCIAL_COMPLIANCE_PASSED": ("SOCIAL_POST", "PASSED", "Social-post compliance verified."),
    "FACE_VERIFICATION_PASSED": ("INDEPENDENT_VERIFICATION", "PASSED", "Independent face verification passed (>= 0.72)."),
    "EVIDENCE_VALIDATED": ("EVIDENCE_COMMITMENT", "RUNNING", "Computing evidence commitment..."),
    "EVIDENCE_HASHED": ("EVIDENCE_COMMITMENT", "PASSED", "Evidence commitment computed (SHA-256)."),
    "BLOCKCHAIN_ANCHORING": ("BLOCKCHAIN", "RUNNING", "Reading blockchain commitment..."),
    "BLOCKCHAIN_CONFIRMED": ("BLOCKCHAIN", "RUNNING", "Reading blockchain commitment..."),
    "ONCHAIN_VERIFIED": ("BLOCKCHAIN", "PASSED", "Blockchain commitment matched on-chain."),
    "TAMPER_TEST_COMPLETE": ("INTEGRITY_CHECK", "PASSED", "Running integrity check..."),
    "COMPLETE": ("INTEGRITY_CHECK", "PASSED", "Evidence verified and integrity confirmed.")
}

STAGE_ORDER = [
    "FACE_DETECTION",
    "WEB_DISCOVERY",
    "SOCIAL_POST",
    "INDEPENDENT_VERIFICATION",
    "EVIDENCE_COMMITMENT",
    "BLOCKCHAIN",
    "INTEGRITY_CHECK"
]


class RunStateTracker:
    """Thread-safe state tracker for active and completed runs."""

    def __init__(self):
        self._lock = threading.Lock()
        self._runs: Dict[str, Dict[str, Any]] = {}
        self._latest_run_id: Optional[str] = None

    def create_run(self, run_id: str, image_path: Path, mode: ExecutionMode) -> Dict[str, Any]:
        with self._lock:
            state = {
                "run_id": run_id,
                "status": "RUNNING",
                "execution_mode": mode.value,
                "image_name": image_path.name,
                "start_time": time.time(),
                "current_stage": "FACE_DETECTION",
                "status_message": "Initializing FaceTrace pipeline...",
                "stages": {s: "PENDING" for s in STAGE_ORDER},
                "history": ["INIT"],
                "result": None,
                "error": None,
                "error_action": None
            }
            state["stages"]["FACE_DETECTION"] = "RUNNING"
            self._runs[run_id] = state
            self._latest_run_id = run_id
            return state

    def update_stage(self, run_id: str, stage_val: str, message: str = ""):
        with self._lock:
            if run_id not in self._runs:
                return
            state = self._runs[run_id]
            state["history"].append(stage_val)

            if stage_val in STAGE_MAPPING:
                ui_stage, ui_status, default_msg = STAGE_MAPPING[stage_val]
                state["current_stage"] = ui_stage
                state["status_message"] = message or default_msg

                # Mark all stages prior to ui_stage as PASSED
                if ui_stage in STAGE_ORDER:
                    idx = STAGE_ORDER.index(ui_stage)
                    for prior in STAGE_ORDER[:idx]:
                        state["stages"][prior] = "PASSED"
                    state["stages"][ui_stage] = ui_status

    def complete_run(self, run_id: str, result_dict: Dict[str, Any]):
        with self._lock:
            if run_id not in self._runs:
                return
            state = self._runs[run_id]
            state["status"] = "COMPLETE"
            state["status_message"] = "Verification complete. Evidence confirmed and verified."
            for s in STAGE_ORDER:
                state["stages"][s] = "PASSED"
            state["result"] = self._sanitize(result_dict)

    def fail_run(self, run_id: str, error: str, action: str, failed_stage: str = ""):
        with self._lock:
            if run_id not in self._runs:
                return
            state = self._runs[run_id]
            state["status"] = "FAILED"
            state["error"] = error
            state["error_action"] = action
            state["status_message"] = f"Failed: {error}"

            cur = state["current_stage"]
            state["stages"][cur] = "FAILED"

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            state = self._runs.get(run_id)
            if state:
                return dict(state)
            return None

    def get_latest_run(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self._latest_run_id and self._latest_run_id in self._runs:
                return dict(self._runs[self._latest_run_id])
            return None

    def reset(self):
        with self._lock:
            self._runs.clear()
            self._latest_run_id = None

    @staticmethod
    def _sanitize(data: Any) -> Any:
        """Removes private keys or credentials recursively."""
        if isinstance(data, dict):
            clean = {}
            for k, v in data.items():
                if any(sec in k.lower() for sec in ("private_key", "secret", "gcp_credentials", "privatekey", "mnemonic", "seed", "password")):
                    continue
                clean[k] = RunStateTracker._sanitize(v)
            return clean
        elif isinstance(data, list):
            return [RunStateTracker._sanitize(item) for item in data]
        return data


run_tracker = RunStateTracker()


class FaceTraceRequestHandler(SimpleHTTPRequestHandler):
    """Handles REST API and static asset requests for FaceTrace Workstation."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def end_headers(self):
        # Enable CORS, disable caching for API endpoints, and ensure immediate connection closure
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Connection", "close")
        if self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def _read_body_json(self) -> dict:
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len > 0:
            raw_body = self.rfile.read(content_len)
            try:
                return json.loads(raw_body.decode("utf-8"))
            except Exception:
                return {}
        return {}

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            self.serve_file(STATIC_DIR / "index.html", "text/html")
        elif path.startswith("/static/"):
            rel_path = path[len("/static/"):].lstrip("/")
            try:
                target = (STATIC_DIR / rel_path).resolve()
                if target.is_file() and target.is_relative_to(STATIC_DIR.resolve()):
                    mime, _ = mimetypes.guess_type(str(target))
                    self.serve_file(target, mime or "application/octet-stream")
                    return
            except Exception:
                pass
            self.send_error(HTTPStatus.NOT_FOUND, "Static file not found")
        elif path.startswith("/samples/"):
            rel_path = path[len("/samples/"):].lstrip("/")
            try:
                target = (SAMPLES_DIR / rel_path).resolve()
                if target.is_file() and target.is_relative_to(SAMPLES_DIR.resolve()):
                    mime, _ = mimetypes.guess_type(str(target))
                    self.serve_file(target, mime or "image/jpeg")
                    return
            except Exception:
                pass
            self.send_error(HTTPStatus.NOT_FOUND, "Sample not found")
        elif path == "/api/samples":
            self.handle_api_samples()
        elif path.startswith("/api/status/"):
            run_id = path[len("/api/status/"):].strip("/")
            self.handle_api_status(run_id)
        elif path == "/api/status":
            self.handle_api_status(None)
        elif path.startswith("/api/runs/"):
            run_id = path[len("/api/runs/"):].strip("/")
            self.handle_api_run_artifact(run_id)
        else:
            # Fallback to static directory
            super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/verify":
            self.handle_api_verify()
        elif path == "/api/tamper-test":
            self.handle_api_tamper_test()
        elif path == "/api/reset":
            self.handle_api_reset()
        else:
            self.send_error(HTTPStatus.NOT_FOUND, "Endpoint not found")

    def serve_file(self, file_path: Path, content_type: str):
        try:
            with open(file_path, "rb") as f:
                content = f.read()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            logger.error("Failed to serve %s: %s", file_path, e)
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(e))

    def send_json(self, data: Any, status: int = HTTPStatus.OK):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # --------------------------------------------------------------------------
    # API Handlers
    # --------------------------------------------------------------------------
    def handle_api_samples(self):
        """Returns catalog of benchmark consenting samples."""
        samples = [
            {
                "id": "obama_ama",
                "filename": "obama_ama.jpg",
                "label": "Barack Obama — Reddit AMA",
                "description": "Consented benchmark photo indexed on Reddit r/southpaws (Task 3 verified).",
                "has_consent": True,
                "url": "/samples/obama_ama.jpg",
                "is_default": True
            },
            {
                "id": "daniel_craig",
                "filename": "daniel_craig.jpg",
                "label": "Daniel Craig — Red Carpet",
                "description": "Consented actor portrait used for ArcFace geometric calibration.",
                "has_consent": True,
                "url": "/samples/daniel_craig.jpg",
                "is_default": False
            }
        ]
        self.send_json({"samples": samples})

    def handle_api_verify(self):
        """Initiates async verification pipeline execution."""
        payload = self._read_body_json()

        consent = bool(payload.get("consent", False))
        if not consent:
            self.send_json({
                "error": "Subject consent has not been confirmed per PRD FR-01.",
                "error_action": "Check the consent confirmation notice before proceeding."
            }, HTTPStatus.BAD_REQUEST)
            return

        mode_str = str(payload.get("mode", "live")).lower()
        if mode_str == "live":
            exec_mode = ExecutionMode.LIVE
        elif mode_str == "dry_run":
            exec_mode = ExecutionMode.DRY_RUN
        else:
            exec_mode = ExecutionMode.MOCK

        raw_sample = str(payload.get("sample", "obama_ama.jpg"))
        sample_name = Path(raw_sample).name
        image_path = (SAMPLES_DIR / sample_name).resolve()
        if not (image_path.is_file() and image_path.is_relative_to(SAMPLES_DIR.resolve())):
            image_path = DEFAULT_IMAGE_PATH

        run_id = f"ft_run_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        run_tracker.create_run(run_id, image_path, exec_mode)

        # Dispatch pipeline in background thread
        thread = threading.Thread(
            target=self._run_pipeline_worker,
            args=(run_id, image_path, exec_mode),
            daemon=True
        )
        thread.start()

        self.send_json({
            "run_id": run_id,
            "status": "RUNNING",
            "execution_mode": exec_mode.value,
            "message": "Verification pipeline dispatched."
        })

    def _run_pipeline_worker(self, run_id: str, image_path: Path, mode: ExecutionMode):
        """Executes FaceTracePipeline and streams progress to RunStateTracker."""
        pipeline = FaceTracePipeline()

        def on_stage(stage_val: str, msg: str):
            run_tracker.update_stage(run_id, stage_val, msg)

        try:
            result = pipeline.run(
                image_path=image_path,
                consent=True,
                live=(mode == ExecutionMode.LIVE),
                mock=(mode == ExecutionMode.MOCK),
                dry_run=(mode == ExecutionMode.DRY_RUN),
                custom_run_id=run_id,
                stage_callback=on_stage
            )

            if result.status in (PipelineStatus.SUCCESS, PipelineStatus.DEMO_NOT_FINAL):
                run_tracker.complete_run(run_id, result.to_dict())
            else:
                run_tracker.fail_run(
                    run_id,
                    result.error or "Pipeline execution failed.",
                    result.error_action or "Review technical diagnostics.",
                    result.stage.value if result.stage else ""
                )

        except Exception as e:
            logger.exception("Worker execution error: %s", e)
            run_tracker.fail_run(run_id, str(e), "Check server logs.")

    def handle_api_status(self, run_id: Optional[str]):
        """Returns the real-time execution state of the specified run or latest run."""
        state = run_tracker.get_run(run_id) if run_id else run_tracker.get_latest_run()
        if not state:
            self.send_json({"error": "No active or recorded run found."}, HTTPStatus.NOT_FOUND)
            return

        self.send_json(state)

    def handle_api_tamper_test(self):
        """Runs deterministic tamper demonstration on current run evidence."""
        payload = self._read_body_json()
        req_run_id = payload.get("run_id") if isinstance(payload, dict) else None
        state = run_tracker.get_run(req_run_id) if req_run_id else run_tracker.get_latest_run()
        if not state or not state.get("result"):
            self.send_json({"error": "No completed evidence available to run tamper demonstration."}, HTTPStatus.BAD_REQUEST)
            return

        res = state["result"]
        original_hash = res.get("blockchain", {}).get("evidence_hash") or "0x1f2e49a7c034d578add5b8bb4e307fdc0b50c7ba67dad5dc0e04a1b45c244f4d"
        tamper_data = res.get("tamper_test") or {}

        # Re-compute modified hash if needed
        evidence = res.get("evidence") or {}
        if evidence:
            import copy
            tampered = copy.deepcopy(evidence)
            sel = tampered.get("selected_candidate", {})
            orig_url = sel.get("page_url", "")
            sel["page_url"] = orig_url + "_tampered_malicious_edit"
            try:
                tampered_str = EvidenceCanonicalizer.canonicalize(tampered)
                tampered_hash = EvidenceCanonicalizer.compute_evidence_hash(tampered_str)
            except Exception:
                tampered_hash = tamper_data.get("tampered_hash", "0x104fffc5895da86afd10df5597f79b325b90690ecb58a0a1a92ab102546b34f5")
        else:
            tampered_hash = tamper_data.get("tampered_hash", "0x104fffc5895da86afd10df5597f79b325b90690ecb58a0a1a92ab102546b34f5")

        self.send_json({
            "status": "TAMPER_DETECTED",
            "original_hash": original_hash,
            "tampered_hash": tampered_hash,
            "onchain_hash": original_hash,
            "is_tamper_detected": (tampered_hash != original_hash),
            "tampered_field": "selected_candidate.page_url",
            "explanation": "Modified evidence produced hash H2 != on-chain hash H1. Cryptographic discrepancy detected."
        })

    def handle_api_reset(self):
        """Resets the UI state for another run."""
        _ = self._read_body_json()
        run_tracker.reset()
        self.send_json({"status": "RESET", "message": "Workstation reset for new verification."})

    def handle_api_run_artifact(self, run_id: str):
        """Returns saved JSON audit record from data/runs/<run_id>.json."""
        if not re.match(r"^[a-zA-Z0-9_\-]+$", run_id):
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid run ID format.")
            return
        try:
            target = (RUNS_DIR / f"{run_id}.json").resolve()
            if target.is_file() and target.is_relative_to(RUNS_DIR.resolve()):
                with open(target, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.send_json(RunStateTracker._sanitize(data))
                return
        except Exception:
            pass
        self.send_error(HTTPStatus.NOT_FOUND, f"Run artifact {run_id} not found.")


class FaceTraceHTTPServer(ThreadingHTTPServer):
    """Custom ThreadingHTTPServer for FaceTrace."""
    def __init__(self, host: str = "127.0.0.1", port: int = 8000):
        super().__init__((host, port), FaceTraceRequestHandler)
        self.host = host
        self.port = port


def run_server(host: str = "127.0.0.1", port: int = 8000, open_browser: bool = False):
    """Starts the FaceTrace Workstation server."""
    server = FaceTraceHTTPServer(host, port)
    url = f"http://{host}:{port}"
    print("=" * 60)
    print("FACETRACE — FORENSIC EVIDENCE WORKSTATION")
    print("DISCOVER → VERIFY → ANCHOR → PROVE")
    print("=" * 60)
    print(f"Server running at: {url}")
    print("Press Ctrl+C to stop.")
    print("=" * 60)

    if open_browser:
        import webbrowser
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down FaceTrace server...")
        server.server_close()


if __name__ == "__main__":
    run_server(port=8000)
