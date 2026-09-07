"""Unit tests for Best-Effort Forensic Investigation architecture.

Verifies:
1. Candidate-level continuation past unreachable/failing candidates.
2. Candidate outcome classification (VERIFIED_MATCH, VERIFIED_WEB_MATCH, UNREACHABLE, REJECTED, etc.).
3. Verification budget enforcement (prioritizes social, limits web, marks budget skipped).
4. RunStateTracker stage state mappings for web-match-only and provider-error scenarios.
5. Generation of dynamic runtime investigation summary.
"""

import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from src.search.models import CandidateOutcome, DiscoveredCandidate, Step2Output
from src.search.orchestrator import SearchOrchestrator
from src.orchestration.pipeline import FaceTracePipeline, PipelineStatus, PipelineStage
from src.ui.server import RunStateTracker, STAGE_ORDER


class TestBestEffortInvestigation(unittest.TestCase):
    """Tests best-effort forensic investigation behavior."""

    def test_candidate_outcome_enum_and_attributes(self):
        """DiscoveredCandidate records candidate_outcome and outcome_reason."""
        cand = DiscoveredCandidate(
            candidate_id="cand_test",
            provider="google_cloud_vision",
            platform="Instagram",
            page_url="https://www.instagram.com/p/abc",
            image_url="https://scontent.cdninstagram.com/xyz.jpg",
            page_title="Photo",
            candidate_outcome=CandidateOutcome.UNREACHABLE.value,
            outcome_reason="HTTP 400 media asset expired"
        )
        self.assertEqual(cand.candidate_outcome, CandidateOutcome.UNREACHABLE.value)
        self.assertIn("HTTP 400", cand.outcome_reason)

    def test_orchestrator_candidate_continuation_and_budget(self):
        """Orchestrator continues past unreachable candidates and records outcomes."""
        orchestrator = SearchOrchestrator(
            max_verification_candidates=4,
            max_social_candidates=2,
            max_web_candidates=2
        )

        # Mock candidates: 3 social, 3 general web
        c1 = DiscoveredCandidate(candidate_id="1", provider="gcv", platform="Instagram", page_url="https://instagram.com/1", image_url="https://ig.com/1.jpg", is_social_domain=True)
        c2 = DiscoveredCandidate(candidate_id="2", provider="gcv", platform="Reddit", page_url="https://reddit.com/2", image_url="https://reddit.com/2.jpg", is_social_domain=True)
        c3 = DiscoveredCandidate(candidate_id="3", provider="gcv", platform="Facebook", page_url="https://facebook.com/3", image_url="https://fb.com/3.jpg", is_social_domain=True)
        c4 = DiscoveredCandidate(candidate_id="4", provider="gcv", platform="imdb.com", page_url="https://imdb.com/4", image_url="https://imdb.com/4.jpg", is_social_domain=False)
        c5 = DiscoveredCandidate(candidate_id="5", provider="gcv", platform="primevideo.com", page_url="https://amazon.com/5", image_url="https://amzn.com/5.jpg", is_social_domain=False)
        c6 = DiscoveredCandidate(candidate_id="6", provider="gcv", platform="news.com", page_url="https://news.com/6", image_url="https://news.com/6.jpg", is_social_domain=False)

        mock_raw = [c1, c2, c3, c4, c5, c6]

        from src.search.models import SearchRequest, FaceInfo, FaceBoundingBox, VerificationDetails, VerificationClassification

        req = SearchRequest(
            job_id="test_job_001",
            original_image=str(Path("samples/obama_ama.jpg").resolve()),
            face=FaceInfo(
                bbox=FaceBoundingBox(x=10, y=10, width=50, height=50),
                embedding=[0.1] * 512
            )
        )

        mock_variants = MagicMock()
        mock_variants.original_path = Path("samples/obama_ama.jpg").resolve()
        mock_variants.face_crop_path = Path("samples/obama_ama.jpg").resolve()
        mock_variants.cleanup = MagicMock()

        with patch.object(orchestrator.query_generator, "generate", return_value=mock_variants):
            with patch.object(orchestrator.cache, "get", return_value=None):
                mock_resp = MagicMock(success=True, candidates=[], latency_ms=10.0)
                with patch.object(orchestrator.provider, "search", return_value=mock_resp):
                    with patch.object(orchestrator.normalizer, "normalize", side_effect=[mock_raw, []]):
                        from src.search.models import RetrievalDetails
                        ret_ok = RetrievalDetails(source_reachable=True, evidence_retrieved=True, image_valid=True)

                        def fake_verify(candidate, original_image_path, query_face, **kwargs):
                            if "instagram" in candidate.page_url:
                                raise Exception("HTTP 400 Bad Request")
                            elif "reddit" in candidate.page_url:
                                return VerificationDetails(classification=VerificationClassification.REJECTED, face_similarity=0.41, retrieval=ret_ok)
                            elif "imdb" in candidate.page_url:
                                return VerificationDetails(classification=VerificationClassification.VERIFIED_DERIVATIVE, face_similarity=0.991, retrieval=ret_ok, face_verified=True)
                            elif "amazon" in candidate.page_url:
                                return VerificationDetails(classification=VerificationClassification.REJECTED, face_similarity=0.52, retrieval=ret_ok)
                            return VerificationDetails(classification=VerificationClassification.REJECTED, face_similarity=0.1, retrieval=ret_ok)

                        with patch.object(orchestrator.verifier, "verify", side_effect=fake_verify):
                            output = orchestrator.search(req)

                            self.assertIsInstance(output, Step2Output)
                            self.assertIsNotNone(output.investigation_summary)

                            summary = output.investigation_summary
                            self.assertEqual(summary["total_discovered"], 6)
                            self.assertEqual(summary["social_candidates"], 3)
                            self.assertEqual(summary["candidates_analyzed"], 4)  # 2 social + 2 web
                            self.assertEqual(summary["unreachable_candidates"], 1)  # Instagram
                            self.assertEqual(summary["verified_web_matches"], 1)  # IMDb
                            self.assertEqual(summary["budget_skipped_candidates"], 2)  # c3 and c6 skipped

                            # Check candidate outcomes
                            self.assertEqual(c1.candidate_outcome, CandidateOutcome.UNREACHABLE.value)
                            self.assertEqual(c4.candidate_outcome, CandidateOutcome.VERIFIED_WEB_MATCH.value)
                            self.assertEqual(c3.candidate_outcome, CandidateOutcome.NOT_ATTEMPTED_DUE_TO_BUDGET.value)
                            self.assertEqual(c6.candidate_outcome, CandidateOutcome.NOT_ATTEMPTED_DUE_TO_BUDGET.value)

    def test_run_state_tracker_web_match_presentation(self):
        """RunStateTracker sets truthful stages when verified web matches exist."""
        tracker = RunStateTracker()
        from src.orchestration.pipeline import ExecutionMode

        tracker.create_run("run_web_match", Path("test.jpg"), ExecutionMode.MOCK)

        summary = {
            "total_discovered": 78,
            "unique_candidates": 66,
            "social_candidates": 16,
            "candidates_analyzed": 25,
            "verified_web_matches": 2,
            "qualifying_social_matches": 0,
            "unreachable_candidates": 11,
            "budget_skipped_candidates": 41,
            "strongest_match": "IMDb — ArcFace 0.9910",
            "social_evidence": "Found, but media assets could not be retrieved.",
            "task3_evidence": "NOT ESTABLISHED",
            "blockchain_status": "NOT ANCHORED"
        }

        tracker.fail_run(
            run_id="run_web_match",
            error="Found 2 verified web matches (IMDb: 0.9910), but no candidate satisfied Task 3 social post provenance.",
            action="Submit a direct social-media specimen.",
            failed_stage="SOCIAL_REQUIREMENT_FAILED",
            title="NO QUALIFYING PUBLIC MATCH",
            investigation_summary=summary
        )

        state = tracker.get_run("run_web_match")
        self.assertIsNotNone(state)
        self.assertEqual(state["stages"]["FACE_DETECTION"], "PASSED")
        self.assertEqual(state["stages"]["WEB_DISCOVERY"], "PASSED")
        self.assertEqual(state["stages"]["SOCIAL_POST"], "COMPLETED_NO_RESULT")
        self.assertEqual(state["stages"]["INDEPENDENT_VERIFICATION"], "PASSED")
        self.assertEqual(state["stages"]["EVIDENCE_COMMITMENT"], "SKIPPED")
        self.assertEqual(state["stages"]["BLOCKCHAIN"], "SKIPPED")
        self.assertEqual(state["stages"]["INTEGRITY_CHECK"], "SKIPPED")
        self.assertEqual(state["investigation_summary"]["verified_web_matches"], 2)
        self.assertEqual(state["investigation_summary"]["unreachable_candidates"], 11)

    def test_run_state_tracker_provider_failure_presentation(self):
        """RunStateTracker sets ERROR and SKIPPED when provider fails."""
        tracker = RunStateTracker()
        from src.orchestration.pipeline import ExecutionMode

        tracker.create_run("run_prov_err", Path("test.jpg"), ExecutionMode.MOCK)

        tracker.fail_run(
            run_id="run_prov_err",
            error="Google Vision API connection timeout.",
            action="Check network connection.",
            failed_stage="SEARCH_ERROR",
            title="SEARCH_ERROR"
        )

        state = tracker.get_run("run_prov_err")
        self.assertIsNotNone(state)
        self.assertEqual(state["stages"]["FACE_DETECTION"], "PASSED")
        self.assertEqual(state["stages"]["WEB_DISCOVERY"], "ERROR")
        self.assertEqual(state["stages"]["SOCIAL_POST"], "SKIPPED")
        self.assertEqual(state["stages"]["INDEPENDENT_VERIFICATION"], "SKIPPED")
        self.assertEqual(state["stages"]["EVIDENCE_COMMITMENT"], "SKIPPED")
        self.assertEqual(state["stages"]["BLOCKCHAIN"], "SKIPPED")
        self.assertEqual(state["stages"]["INTEGRITY_CHECK"], "SKIPPED")


if __name__ == "__main__":
    unittest.main()
