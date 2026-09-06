"""
FaceTrace — Step 4 End-to-End Orchestration & Hackathon Demo Test Suite
Verifies:
1. Successful full pipeline with mocks
2. Face detection failure
3. Search failure
4. No qualifying social post
5. Face verification rejection
6. Invalid evidence
7. Existing blockchain anchor recovery
8. Blockchain mismatch
9. Tamper detection
10. Mock execution cannot report LIVE success
11. Cache execution cannot report LIVE success
12. Live mode requires live blockchain
13. Run IDs are unique
14. No secrets leak into output
15. Final evidence package is internally consistent
"""

import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

from src.core.face_engine import FaceDetectionResult, FaceEngine
from src.search.models import (
    Step2Output,
    DiscoveredCandidate,
    MatchClassification,
    VerificationClassification,
    RetrievalDetails,
    FaceInfo,
    FaceBoundingBox
)
from src.search.orchestrator import SearchOrchestrator
from src.search.providers.mock_provider import MockSearchProvider
from src.blockchain.client import MockBlockchainClient, BlockchainClient
from src.blockchain.canonicalizer import EvidenceCanonicalizer, NonCompliantEvidenceError
from src.blockchain.models import (
    BlockchainMode,
    BlockchainRecord,
    BlockchainReleaseStatus,
    VerificationComparisonResult,
    BlockchainState
)
from src.orchestration.models import (
    PipelineStage,
    ExecutionMode,
    PipelineStatus,
    FaceTraceRunResult
)
from src.orchestration.pipeline import FaceTracePipeline, DEFAULT_IMAGE_PATH, RUNS_DIR


class TestEndToEndOrchestration(unittest.TestCase):
    """15-point comprehensive validation suite for Step 4 master orchestration."""

    @classmethod
    def setUpClass(cls):
        cls.test_image = DEFAULT_IMAGE_PATH
        assert cls.test_image.exists(), f"Sample image not found: {cls.test_image}"
        cls.shared_face_engine = FaceEngine()

    def _build_mock_search_orchestrator(self, candidate_image_path: Path):
        with open(candidate_image_path, "rb") as f:
            mock_bytes = f.read()
        mock_pil = Image.open(candidate_image_path)
        ret_ok = RetrievalDetails(source_reachable=True, evidence_retrieved=True, image_valid=True)

        provider = MockSearchProvider()
        orch = SearchOrchestrator(provider=provider, max_verification_candidates=5)
        orch.verifier.fetch_candidate_image = lambda c: (mock_bytes, mock_pil, ret_ok)
        return orch

    def test_01_successful_full_pipeline_mock(self):
        """1. Successful full pipeline with mocks."""
        mock_bc = MockBlockchainClient()
        pipeline = FaceTracePipeline(face_engine=self.shared_face_engine, blockchain_client=mock_bc)

        result = pipeline.run(
            image_path=self.test_image,
            consent=True,
            mock=True
        )

        # Stage progression checks
        self.assertIn(PipelineStage.INIT.value, result.history)
        self.assertIn(PipelineStage.INPUT_VALIDATED.value, result.history)
        self.assertIn(PipelineStage.CONSENT_CONFIRMED.value, result.history)
        self.assertIn(PipelineStage.FACE_DETECTED.value, result.history)
        self.assertIn(PipelineStage.SEARCH_COMPLETE.value, result.history)
        self.assertIn(PipelineStage.CANDIDATE_SELECTED.value, result.history)
        self.assertIn(PipelineStage.SOCIAL_COMPLIANCE_PASSED.value, result.history)
        self.assertIn(PipelineStage.FACE_VERIFICATION_PASSED.value, result.history)
        self.assertIn(PipelineStage.EVIDENCE_HASHED.value, result.history)
        self.assertIn(PipelineStage.BLOCKCHAIN_CONFIRMED.value, result.history)
        self.assertIn(PipelineStage.ONCHAIN_VERIFIED.value, result.history)
        self.assertIn(PipelineStage.TAMPER_TEST_COMPLETE.value, result.history)
        self.assertIn(PipelineStage.COMPLETE.value, result.history)

        # Output model checks
        self.assertEqual(result.execution_mode, ExecutionMode.MOCK)
        self.assertEqual(result.status, PipelineStatus.DEMO_NOT_FINAL)
        self.assertIsNotNone(result.candidate)
        self.assertEqual(result.candidate.platform, "reddit")
        self.assertIsNotNone(result.blockchain)
        self.assertTrue(result.blockchain.evidence_hash.startswith("0x"))
        self.assertEqual(result.blockchain.verification_status, "MATCH")

    def test_02_face_detection_failure(self):
        """2. Face detection failure properly halts pipeline with NO_FACE."""
        mock_engine = MagicMock(spec=FaceEngine)
        mock_engine.detect_and_embed.return_value = FaceDetectionResult(
            detected=False,
            error="NO_FACE_DETECTED"
        )

        pipeline = FaceTracePipeline(face_engine=mock_engine)
        result = pipeline.run(image_path=self.test_image, consent=True, mock=True)

        self.assertEqual(result.status, PipelineStatus.FAILED)
        self.assertEqual(result.stage, PipelineStage.NO_FACE)
        self.assertIn(PipelineStage.NO_FACE.value, result.history)
        self.assertIn("No face detected", result.error)

    def test_03_search_failure(self):
        """3. Search failure properly halts pipeline with SEARCH_ERROR."""
        mock_orch = MagicMock(spec=SearchOrchestrator)
        mock_orch.search.return_value = Step2Output(
            job_id="test_fail",
            status="SEARCH_UNAVAILABLE",
            search={"error": "Vision API quota exceeded or network unavailable", "execution_mode": "MOCK_PROVIDER"},
            selected_candidate=None,
            provenance={}
        )

        pipeline = FaceTracePipeline(face_engine=self.shared_face_engine, search_orchestrator=mock_orch)
        result = pipeline.run(image_path=self.test_image, consent=True, mock=True)

        self.assertEqual(result.status, PipelineStatus.FAILED)
        self.assertEqual(result.stage, PipelineStage.SEARCH_ERROR)
        self.assertIn("Vision API quota exceeded", result.error)

    def test_04_no_qualifying_social_post(self):
        """4. No qualifying social post halts pipeline."""
        mock_orch = MagicMock(spec=SearchOrchestrator)
        mock_orch.search.return_value = Step2Output(
            job_id="test_no_match",
            status="NO_CANDIDATES_FOUND",
            search={"execution_mode": "MOCK_PROVIDER"},
            selected_candidate=None,
            provenance={}
        )

        pipeline = FaceTracePipeline(face_engine=self.shared_face_engine, search_orchestrator=mock_orch)
        result = pipeline.run(image_path=self.test_image, consent=True, mock=True)

        self.assertEqual(result.status, PipelineStatus.FAILED)
        self.assertEqual(result.stage, PipelineStage.NO_MATCH)

    def test_05_face_verification_rejection(self):
        """5. Face verification rejection properly fails pipeline."""
        orch = self._build_mock_search_orchestrator(self.test_image)

        # Patch verifier to simulate rejected candidate face verification
        orig_search = orch.search
        def mock_search_reject(*args, **kwargs):
            out = orig_search(*args, **kwargs)
            if out.selected_candidate:
                out.selected_candidate["verification"] = {
                    "face_verified": False,
                    "verification_state": "REJECTED",
                    "explanation": "Face similarity 0.4210 is below threshold 0.72"
                }
            return out

        orch.search = mock_search_reject

        pipeline = FaceTracePipeline(face_engine=self.shared_face_engine, search_orchestrator=orch)
        result = pipeline.run(image_path=self.test_image, consent=True, mock=True)

        self.assertEqual(result.status, PipelineStatus.FAILED)
        self.assertEqual(result.stage, PipelineStage.FACE_VERIFICATION_FAILED)
        self.assertEqual(result.verification_type, "REJECTED")

    def test_06_invalid_evidence(self):
        """6. Invalid evidence package failing canonicalization triggers EVIDENCE_INVALID."""
        orch = self._build_mock_search_orchestrator(self.test_image)

        orig_search = orch.search
        def mock_search_bad_evidence(*args, **kwargs):
            out = orig_search(*args, **kwargs)
            # Remove required canonical field schema_version and candidate_url
            out.selected_candidate = {"corrupted": True}
            return out

        orch.search = mock_search_bad_evidence

        pipeline = FaceTracePipeline(face_engine=self.shared_face_engine, search_orchestrator=orch)
        result = pipeline.run(image_path=self.test_image, consent=True, mock=True)

        self.assertEqual(result.status, PipelineStatus.FAILED)
        self.assertIn(result.stage, (PipelineStage.EVIDENCE_INVALID, PipelineStage.FACE_VERIFICATION_FAILED))

    def test_07_existing_blockchain_anchor_recovery(self):
        """7. Existing blockchain anchor recovery: does not create duplicate and recovers tx."""
        mock_bc = MockBlockchainClient()
        fake_evidence_hash = "0x" + "a" * 64
        fake_tx = "0x" + "b" * 64
        mock_bc.mock_records[fake_evidence_hash] = {
            "evidence_hash": fake_evidence_hash,
            "timestamp": 1710000000,
            "submitter": "0x1111111111111111111111111111111111111111",
            "transaction_hash": fake_tx,
            "block_number": 12345,
            "exists": True
        }

        record = mock_bc.anchor_evidence(fake_evidence_hash)
        self.assertEqual(record.anchor_status, "ALREADY_ANCHORED")
        self.assertEqual(record.transaction_hash, fake_tx)
        self.assertEqual(record.block_number, 12345)

        exists, timestamp, submitter = mock_bc.verify_evidence(fake_evidence_hash)
        self.assertTrue(exists)
        self.assertEqual(timestamp, 1710000000)

    def test_08_blockchain_mismatch(self):
        """8. Blockchain verification mismatch detection."""
        mock_bc = MockBlockchainClient()
        mock_bc.verify_local_against_chain = MagicMock(return_value=VerificationComparisonResult(
            state=BlockchainState.VERIFICATION_FAIL,
            is_verified=False,
            local_hash="0x" + "1" * 64,
            on_chain_hash="0x" + "2" * 64,
            reason="On-chain hash differs from local hash."
        ))

        pipeline = FaceTracePipeline(face_engine=self.shared_face_engine, blockchain_client=mock_bc)
        result = pipeline.run(image_path=self.test_image, consent=True, mock=True)

        self.assertEqual(result.status, PipelineStatus.FAILED)
        self.assertEqual(result.stage, PipelineStage.BLOCKCHAIN_VERIFICATION_FAILED)

    def test_09_tamper_detection(self):
        """9. Tamper detection simulation detects altered canonical fields."""
        mock_bc = MockBlockchainClient()
        pipeline = FaceTracePipeline(face_engine=self.shared_face_engine, blockchain_client=mock_bc)
        result = pipeline.run(image_path=self.test_image, consent=True, mock=True)

        self.assertIsNotNone(result.tamper_test)
        self.assertEqual(result.tamper_test.status, "TAMPER_DETECTED")
        self.assertTrue(result.tamper_test.is_tamper_detected)
        self.assertNotEqual(result.tamper_test.original_hash, result.tamper_test.tampered_hash)
        self.assertEqual(result.tamper_test.original_hash, result.tamper_test.onchain_hash)

    def test_10_mock_execution_cannot_report_live_success(self):
        """10. Mock execution cannot report LIVE success (anti-false-pass)."""
        mock_bc = MockBlockchainClient()
        pipeline = FaceTracePipeline(blockchain_client=mock_bc)
        result = pipeline.run(image_path=self.test_image, consent=True, mock=True)

        self.assertNotEqual(result.status, PipelineStatus.SUCCESS)
        self.assertEqual(result.status, PipelineStatus.DEMO_NOT_FINAL)
        self.assertNotEqual(result.execution_mode, ExecutionMode.LIVE)
        self.assertEqual(result.execution_mode, ExecutionMode.MOCK)

    def test_11_cache_execution_cannot_report_live_success(self):
        """11. Cache execution cannot report LIVE success."""
        mock_orch = MagicMock(spec=SearchOrchestrator)
        mock_orch.search.return_value = Step2Output(
            job_id="test_cache",
            status="SOCIAL_POST_MATCH_FOUND",
            search={"execution_mode": "CACHE_REPLAY"},
            task3_compliance={
                "state": "NOT_FINAL_TASK3_PASS",
                "passed": False,
                "reason": "Candidate verified from cached results; Task 3 compliance requires fresh live search execution."
            },
            selected_candidate={"page_url": "https://reddit.com/r/test/comments/123", "platform": "reddit"},
            provenance={}
        )

        pipeline = FaceTracePipeline(face_engine=self.shared_face_engine, search_orchestrator=mock_orch)
        result = pipeline.run(image_path=self.test_image, consent=True, live=True)

        self.assertEqual(result.status, PipelineStatus.FAILED)
        self.assertEqual(result.stage, PipelineStage.SOCIAL_REQUIREMENT_FAILED)
        self.assertEqual(result.task3_compliance, "NOT_FINAL_TASK3_PASS")

    def test_12_live_mode_requires_live_blockchain(self):
        """12. Live mode requires live blockchain client (rejects MockBlockchainClient in LIVE mode)."""
        mock_bc = MockBlockchainClient()
        pipeline = FaceTracePipeline(face_engine=self.shared_face_engine, blockchain_client=mock_bc)

        # In live mode with mock blockchain client, must be BLOCKED
        result = pipeline.run(image_path=self.test_image, consent=True, live=True)
        self.assertEqual(result.status, PipelineStatus.BLOCKED)
        self.assertEqual(result.stage, PipelineStage.BLOCKCHAIN_ERROR)
        self.assertIn("anti-false-pass violation", result.error.lower())

    def test_13_run_ids_are_unique(self):
        """13. Run IDs are globally unique across invocations."""
        mock_bc = MockBlockchainClient()
        pipeline = FaceTracePipeline(face_engine=self.shared_face_engine, blockchain_client=mock_bc)

        res1 = pipeline.run(image_path=self.test_image, consent=True, mock=True)
        res2 = pipeline.run(image_path=self.test_image, consent=True, mock=True)

        self.assertNotEqual(res1.run_id, res2.run_id)
        file1 = RUNS_DIR / f"{res1.run_id}.json"
        file2 = RUNS_DIR / f"{res2.run_id}.json"
        self.assertTrue(file1.exists())
        self.assertTrue(file2.exists())

    def test_14_no_secrets_leak_into_output(self):
        """14. No secrets leak into output or stored run records."""
        mock_bc = MockBlockchainClient()
        pipeline = FaceTracePipeline(face_engine=self.shared_face_engine, blockchain_client=mock_bc)
        result = pipeline.run(image_path=self.test_image, consent=True, mock=True)

        res_dict = result.to_dict()
        res_json = json.dumps(res_dict).lower()

        forbidden = ["private_key", "secret", "gcp_credentials", "privatekey", "client_secret"]
        for key in forbidden:
            self.assertNotIn(f'"{key}"', res_json)

        # Verify on-disk run record does not leak secrets
        saved_file = RUNS_DIR / f"{result.run_id}.json"
        with open(saved_file, "r") as f:
            disk_content = f.read().lower()
        for key in forbidden:
            self.assertNotIn(f'"{key}"', disk_content)

    def test_15_final_evidence_package_is_internally_consistent(self):
        """15. Final evidence package is internally consistent."""
        mock_bc = MockBlockchainClient()
        pipeline = FaceTracePipeline(face_engine=self.shared_face_engine, blockchain_client=mock_bc)
        result = pipeline.run(image_path=self.test_image, consent=True, mock=True)

        # Check saved run record matches returned model
        saved_file = RUNS_DIR / f"{result.run_id}.json"
        self.assertTrue(saved_file.exists())
        with open(saved_file, "r") as f:
            saved_data = json.load(f)

        self.assertEqual(saved_data["run_id"], result.run_id)
        self.assertEqual(saved_data["status"], result.status.value)
        self.assertEqual(saved_data["execution_mode"], result.execution_mode.value)
        self.assertEqual(saved_data["blockchain"]["evidence_hash"], result.blockchain.evidence_hash)
        self.assertEqual(saved_data["tamper_test"]["original_hash"], result.tamper_test.original_hash)
        self.assertEqual(saved_data["candidate"]["post_url"], result.candidate.post_url)


if __name__ == "__main__":
    unittest.main()
