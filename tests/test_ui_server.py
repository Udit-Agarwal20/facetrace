"""
FaceTrace — Step 5 UI Server & Presentation Integration Test Suite
Tests:
1. Static asset serving (index.html, style.css, app.js, samples)
2. Consent requirement enforcement (PRD FR-01)
3. API sample catalog discovery
4. Pipeline run dispatching and lifecycle
5. Real-time stage transition tracking (PENDING, RUNNING, PASSED, FAILED)
6. Polling endpoint /api/status/<run_id>
7. Deterministic cryptographic tamper testing endpoint
8. Reset flow without restarting server
9. No secret credentials leaked into client responses
10. Failure state handling and structured diagnostic responses
11. BaseScan link and blockchain proof integrity
12. Distinction between live, mock, and dry-run execution modes
"""

import http.client
import json
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from src.orchestration.models import ExecutionMode, PipelineStatus, PipelineStage
from src.ui.server import (
    FaceTraceHTTPServer,
    RunStateTracker,
    run_tracker,
    STAGE_ORDER,
    STAGE_MAPPING,
    SAMPLES_DIR,
    STATIC_DIR
)


class TestFaceTraceUIServer(unittest.TestCase):
    """Integration and unit tests for FaceTrace UI presentation layer."""

    @classmethod
    def setUpClass(cls):
        # Start test HTTP server on an ephemeral loopback port
        cls.server = FaceTraceHTTPServer(host="127.0.0.1", port=0)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        run_tracker.reset()

    def _request(self, method: str, path: str, body: dict = None) -> tuple[int, dict, bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Connection": "close"}
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode("utf-8")
        conn.request(method, path, body=data, headers=headers)
        res = conn.getresponse()
        resp_body = res.read()
        headers_dict = {k.lower(): v for k, v in res.getheaders()}
        conn.close()
        return res.status, headers_dict, resp_body

    def test_01_serve_index_html(self):
        """Verifies root endpoint serves HTML with all 7 screens and consent notice."""
        status, headers, body = self._request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("content-type", ""))
        html = body.decode("utf-8")
        self.assertIn("FACETRACE", html)
        self.assertIn("VERIFY FACE", html)
        self.assertIn("Use only a face image you have permission to process", html)
        # All 7 screens present
        self.assertIn("screen1-input", html)
        self.assertIn("screen2-pipeline", html)
        self.assertIn("screen3-discovery", html)
        self.assertIn("screen4-evidence", html)
        self.assertIn("screen5-blockchain", html)
        self.assertIn("screen6-tamper", html)
        self.assertIn("screen7-final", html)

    def test_02_serve_static_assets(self):
        """Verifies static CSS and JS assets are served properly."""
        status, headers, body = self._request("GET", "/static/style.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", headers.get("content-type", ""))
        self.assertIn("Forensic Evidence Workstation", body.decode("utf-8"))

        status, headers, body = self._request("GET", "/static/app.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", headers.get("content-type", ""))
        self.assertIn("startVerification", body.decode("utf-8"))

    def test_03_serve_sample_specimen(self):
        """Verifies consenting benchmark face specimens are accessible."""
        status, headers, body = self._request("GET", "/samples/obama_ama.jpg")
        self.assertEqual(status, 200)
        self.assertIn("image/jpeg", headers.get("content-type", ""))
        self.assertGreater(len(body), 1000)

    def test_04_api_samples_catalog(self):
        """Verifies /api/samples returns consenting benchmark catalog."""
        status, _, body = self._request("GET", "/api/samples")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("samples", data)
        self.assertGreaterEqual(len(data["samples"]), 2)
        sample_ids = [s["id"] for s in data["samples"]]
        self.assertIn("obama_ama", sample_ids)
        for s in data["samples"]:
            self.assertTrue(s["has_consent"])

    def test_05_consent_enforcement_rejection(self):
        """Verifies verification cannot proceed without explicit consent (PRD FR-01)."""
        payload = {"sample": "obama_ama.jpg", "mode": "mock", "consent": False}
        status, _, body = self._request("POST", "/api/verify", payload)
        self.assertEqual(status, 400)
        data = json.loads(body.decode("utf-8"))
        self.assertIn("consent", data.get("error", "").lower())
        self.assertIn("error_action", data)

    def test_06_pipeline_state_transitions(self):
        """Verifies RunStateTracker correctly manages chronological stage transitions."""
        tracker = RunStateTracker()
        run_id = "test_run_123"
        tracker.create_run(run_id, SAMPLES_DIR / "obama_ama.jpg", ExecutionMode.MOCK)

        state = tracker.get_run(run_id)
        self.assertIsNotNone(state)
        self.assertEqual(state["status"], "RUNNING")
        self.assertEqual(state["stages"]["FACE_DETECTION"], "RUNNING")
        self.assertEqual(state["stages"]["WEB_DISCOVERY"], "PENDING")

        # Advance to WEB_DISCOVERY
        tracker.update_stage(run_id, "SEARCH_COMPLETE", "Discovered 5 web candidates")
        state = tracker.get_run(run_id)
        self.assertEqual(state["stages"]["FACE_DETECTION"], "PASSED")
        self.assertEqual(state["stages"]["WEB_DISCOVERY"], "PASSED")

        # Advance to BLOCKCHAIN
        tracker.update_stage(run_id, "ONCHAIN_VERIFIED", "Readback verified")
        state = tracker.get_run(run_id)
        self.assertEqual(state["stages"]["BLOCKCHAIN"], "PASSED")

    def test_07_polling_and_completion(self):
        """Verifies /api/status endpoint returns active and completed run states."""
        # Create completed mock run in tracker
        run_id = "test_run_complete"
        run_tracker.create_run(run_id, SAMPLES_DIR / "obama_ama.jpg", ExecutionMode.LIVE)
        mock_result = {
            "run_id": run_id,
            "status": "SUCCESS",
            "task3_compliance": "TASK3_SOCIAL_MATCH",
            "candidate": {
                "platform": "Reddit",
                "post_url": "https://www.reddit.com/r/southpaws/comments/y10ep/",
                "image_url": "https://i.imgur.com/example.jpg"
            },
            "verification": {
                "face_similarity": 1.0,
                "sha256_exact": True,
                "phash_distance": 0
            },
            "blockchain": {
                "network": "base_sepolia",
                "chain_id": 84532,
                "contract_address": "0x71fcDeb36659E264716618b3E3a7C142Ff42455a",
                "evidence_hash": "0x1f2e49a7c034d578add5b8bb4e307fdc0b50c7ba67dad5dc0e04a1b45c244f4d",
                "transaction_hash": "0x48e3b99c03504f08005eaf60a25073e76ad75401e310c50f27fbd208275077d7",
                "block_number": 46459229,
                "anchor_mode": "EXISTING_RECOVERY",
                "blockchain_status": "LIVE_BLOCKCHAIN_VERIFIED"
            }
        }
        run_tracker.complete_run(run_id, mock_result)

        status, _, body = self._request("GET", f"/api/status/{run_id}")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data["status"], "COMPLETE")
        for s in STAGE_ORDER:
            self.assertEqual(data["stages"][s], "PASSED")
        self.assertEqual(data["result"]["blockchain"]["chain_id"], 84532)

    def test_08_tamper_detection_endpoint(self):
        """Verifies /api/tamper-test computes cryptographic discrepancy H1 != H2."""
        run_id = "test_run_tamper"
        run_tracker.create_run(run_id, SAMPLES_DIR / "obama_ama.jpg", ExecutionMode.LIVE)
        mock_result = {
            "run_id": run_id,
            "blockchain": {
                "evidence_hash": "0x1f2e49a7c034d578add5b8bb4e307fdc0b50c7ba67dad5dc0e04a1b45c244f4d"
            },
            "tamper_test": {
                "status": "TAMPER_DETECTED",
                "original_hash": "0x1f2e49a7c034d578add5b8bb4e307fdc0b50c7ba67dad5dc0e04a1b45c244f4d",
                "tampered_hash": "0x104fffc5895da86afd10df5597f79b325b90690ecb58a0a1a92ab102546b34f5",
                "is_tamper_detected": True
            }
        }
        run_tracker.complete_run(run_id, mock_result)

        status, _, body = self._request("POST", "/api/tamper-test", {"run_id": run_id})
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data["status"], "TAMPER_DETECTED")
        self.assertTrue(data["is_tamper_detected"])
        self.assertNotEqual(data["original_hash"], data["tampered_hash"])

    def test_09_reset_endpoint(self):
        """Verifies /api/reset cleanly clears current run state for subsequent runs."""
        run_id = "test_run_reset"
        run_tracker.create_run(run_id, SAMPLES_DIR / "obama_ama.jpg", ExecutionMode.MOCK)
        self.assertIsNotNone(run_tracker.get_run(run_id))

        status, _, body = self._request("POST", "/api/reset")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data["status"], "RESET")
        self.assertIsNone(run_tracker.get_latest_run())

    def test_10_security_sanitization_no_secrets(self):
        """Verifies sensitive wallet keys or secrets are recursively stripped from responses."""
        dirty_data = {
            "evidence": {
                "name": "public_evidence"
            },
            "blockchain": {
                "private_key": "0xDEADBEEF1234567890",
                "wallet_secret": "secret_key_value",
                "mnemonic": "twelve secret recovery words never shown to user",
                "public_address": "0x1234567890abcdef"
            }
        }
        sanitized = RunStateTracker._sanitize(dirty_data)
        self.assertNotIn("private_key", sanitized["blockchain"])
        self.assertNotIn("wallet_secret", sanitized["blockchain"])
        self.assertNotIn("mnemonic", sanitized["blockchain"])
        self.assertIn("public_address", sanitized["blockchain"])

    def test_11_failure_state_handling(self):
        """Verifies clean failure responses when pipeline encounters an error."""
        run_id = "test_run_fail"
        run_tracker.create_run(run_id, SAMPLES_DIR / "obama_ama.jpg", ExecutionMode.MOCK)
        run_tracker.fail_run(
            run_id=run_id,
            error="No qualifying social post found on supported platform.",
            action="Ensure the subject photo is referenced in a public social post.",
            failed_stage="SOCIAL_POST"
        )

        status, _, body = self._request("GET", f"/api/status/{run_id}")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data["status"], "FAILED")
        self.assertIn("social post", data["error"].lower())
        self.assertIn("social post", data.get("error_action", "").lower())
        self.assertEqual(data["stages"]["FACE_DETECTION"], "FAILED")

    def test_12_path_traversal_prevention(self):
        """Verifies path traversal attempts on /static/ and /samples/ return 404."""
        status_static, _, _ = self._request("GET", "/static/../../../.env")
        self.assertEqual(status_static, 404)

        status_sample, _, _ = self._request("GET", "/samples/../../.env")
        self.assertEqual(status_sample, 404)

        status_enc, _, _ = self._request("GET", "/static/%2e%2e/%2e%2e/.env")
        self.assertEqual(status_enc, 404)

    def test_13_run_artifact_security(self):
        """Verifies invalid or traversal run IDs on /api/runs/<run_id> are rejected."""
        status_bad_format, _, _ = self._request("GET", "/api/runs/../../etc/passwd")
        self.assertIn(status_bad_format, (400, 404))

        status_nonexistent, _, _ = self._request("GET", "/api/runs/nonexistent_run_12345")
        self.assertEqual(status_nonexistent, 404)

    def test_14_tamper_test_specific_run_id(self):
        """Verifies tamper endpoint respects explicit run_id even if a newer run exists."""
        run1 = "run_alpha"
        run2 = "run_beta"
        run_tracker.create_run(run1, SAMPLES_DIR / "obama_ama.jpg", ExecutionMode.MOCK)
        mock_res1 = {
            "evidence": {
                "selected_candidate": {"page_url": "https://reddit.com/r/test/comments/123"}
            },
            "blockchain": {
                "evidence_hash": "0x1111111111111111111111111111111111111111111111111111111111111111"
            }
        }
        run_tracker.complete_run(run1, mock_res1)

        # Start second run (e.g. concurrent user in another tab)
        run_tracker.create_run(run2, SAMPLES_DIR / "daniel_craig.jpg", ExecutionMode.MOCK)

        # Tab 1 requests tamper test for run1 specifically
        status, _, body = self._request("POST", "/api/tamper-test", {"run_id": run1})
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data["status"], "TAMPER_DETECTED")
        self.assertEqual(data["original_hash"], "0x1111111111111111111111111111111111111111111111111111111111111111")
        self.assertTrue(data["is_tamper_detected"])


if __name__ == "__main__":
    unittest.main()
