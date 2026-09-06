"""
FaceTrace Step 2 Acceptance Test Suite.
Tests the full Acceptance Matrix (Cases 1-10 per Section 23), Execution Modes,
URL Classification edge cases, and Retrieval failure robustness.
"""

from pathlib import Path
import sys
import unittest

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from src.search.models import (
    DiscoveredCandidate,
    VerificationDetails,
    VerificationClassification,
    MatchClassification,
    ExecutionMode,
    Task3ComplianceState,
    RetrievalDetails
)
from src.search.compliance import evaluate_task3_candidate
from src.search.platform_classifier import PlatformClassifier


class TestStep2AcceptanceMatrix(unittest.TestCase):
    """Verifies all 10 Acceptance Matrix cases from Section 23 & 46."""

    def setUp(self):
        self.ret_success = RetrievalDetails(source_reachable=True, evidence_retrieved=True, image_valid=True)
        self.ret_failed = RetrievalDetails(source_reachable=True, evidence_retrieved=False, image_valid=False, error="404 Not Found")

    def test_case_1_qualifying_live_social_post(self):
        """Case 1: Social domain + post URL + live search + retrievable + face verified -> TASK3_SOCIAL_MATCH"""
        cand = DiscoveredCandidate(
            candidate_id="cand_1",
            provider="google_vision",
            page_url="https://www.reddit.com/r/movies/comments/12345/daniel_craig/",
            image_url="https://i.redd.it/photo.jpg",
            is_social_domain=True,
            is_post_url=True,
            platform="reddit",
            retrieval=self.ret_success
        )
        ver = VerificationDetails(
            classification=VerificationClassification.VERIFIED_DERIVATIVE,
            face_verified=True,
            face_similarity=0.9638,
            faces_detected=1,
            retrieval=self.ret_success
        )
        ctx = {"execution_mode": ExecutionMode.LIVE_EXTERNAL_SEARCH}
        res = evaluate_task3_candidate(cand, ver, ctx)

        self.assertEqual(res.state, Task3ComplianceState.TASK3_SOCIAL_MATCH)
        self.assertTrue(res.passed)
        self.assertEqual(len(res.failed_gates), 0)

    def test_case_2_social_post_face_rejected(self):
        """Case 2: Social domain + post URL + face rejected -> REJECTED"""
        cand = DiscoveredCandidate(
            candidate_id="cand_2",
            provider="google_vision",
            page_url="https://www.instagram.com/p/C12345/",
            image_url="https://cdn.instagram.com/img.jpg",
            is_social_domain=True,
            is_post_url=True,
            platform="instagram",
            retrieval=self.ret_success
        )
        ver = VerificationDetails(
            classification=VerificationClassification.REJECTED,
            face_verified=False,
            face_similarity=0.1500,
            faces_detected=1,
            retrieval=self.ret_success
        )
        ctx = {"execution_mode": ExecutionMode.LIVE_EXTERNAL_SEARCH}
        res = evaluate_task3_candidate(cand, ver, ctx)

        self.assertEqual(res.state, Task3ComplianceState.REJECTED)
        self.assertFalse(res.passed)
        self.assertTrue(any("ARCFACE_VERIFIED" in g for g in res.failed_gates))

    def test_case_3_news_article_face_verified(self):
        """Case 3: News article + verified image/face -> WEB_MATCH_ONLY"""
        cand = DiscoveredCandidate(
            candidate_id="cand_3",
            provider="google_vision",
            page_url="https://www.wbaltv.com/article/daniel-craig/12345",
            image_url="https://kubrick.htvapps.com/images/daniel.jpg",
            is_social_domain=False,
            is_post_url=False,
            platform=None,
            retrieval=self.ret_success
        )
        ver = VerificationDetails(
            classification=VerificationClassification.VERIFIED_DERIVATIVE,
            face_verified=True,
            face_similarity=0.9500,
            faces_detected=1,
            retrieval=self.ret_success
        )
        ctx = {"execution_mode": ExecutionMode.LIVE_EXTERNAL_SEARCH}
        res = evaluate_task3_candidate(cand, ver, ctx)

        self.assertEqual(res.state, Task3ComplianceState.WEB_MATCH_ONLY)
        self.assertFalse(res.passed)
        self.assertTrue(any("SOCIAL_DOMAIN" in g for g in res.failed_gates))

    def test_case_4_search_provider_url_rejected(self):
        """Case 4: Google/search-provider URL -> REJECTED"""
        cand = DiscoveredCandidate(
            candidate_id="cand_4",
            provider="google_vision",
            page_url="https://lens.google.com/search?p=123",
            image_url="https://lens.google.com/img.jpg",
            is_social_domain=False,
            is_post_url=False,
            retrieval=self.ret_success
        )
        ver = VerificationDetails(
            classification=VerificationClassification.VERIFIED_EXACT,
            face_verified=True,
            face_similarity=1.0,
            retrieval=self.ret_success
        )
        ctx = {"execution_mode": ExecutionMode.LIVE_EXTERNAL_SEARCH}
        res = evaluate_task3_candidate(cand, ver, ctx)

        self.assertEqual(res.state, Task3ComplianceState.REJECTED)
        self.assertFalse(res.passed)
        self.assertTrue(any("EXTERNAL_SOURCE" in g for g in res.failed_gates))

    def test_case_5_generic_social_homepage_rejected(self):
        """Case 5: Generic Instagram/Facebook homepage -> REJECTED"""
        cand = DiscoveredCandidate(
            candidate_id="cand_5",
            provider="google_vision",
            page_url="https://www.facebook.com/",
            is_social_domain=True,
            is_post_url=False,
            platform="facebook",
            retrieval=self.ret_success
        )
        ver = VerificationDetails(
            classification=VerificationClassification.VERIFIED_DERIVATIVE,
            face_verified=True,
            face_similarity=0.9100,
            faces_detected=1,
            retrieval=self.ret_success
        )
        ctx = {"execution_mode": ExecutionMode.LIVE_EXTERNAL_SEARCH}
        res = evaluate_task3_candidate(cand, ver, ctx)

        self.assertEqual(res.state, Task3ComplianceState.REJECTED)
        self.assertFalse(res.passed)
        self.assertTrue(any("POST_LIKE_URL" in g for g in res.failed_gates))

    def test_case_6_social_profile_not_post(self):
        """Case 6: Social profile URL but not content/post URL -> REJECTED AS TASK3 MATCH"""
        cand = DiscoveredCandidate(
            candidate_id="cand_6",
            provider="google_vision",
            page_url="https://instagram.com/danielcraigfanclub",
            is_social_domain=True,
            is_post_url=False,
            platform="instagram",
            retrieval=self.ret_success
        )
        ver = VerificationDetails(
            classification=VerificationClassification.VERIFIED_DERIVATIVE,
            face_verified=True,
            face_similarity=0.8900,
            faces_detected=1,
            retrieval=self.ret_success
        )
        ctx = {"execution_mode": ExecutionMode.LIVE_EXTERNAL_SEARCH}
        res = evaluate_task3_candidate(cand, ver, ctx)

        self.assertEqual(res.state, Task3ComplianceState.REJECTED)
        self.assertFalse(res.passed)
        self.assertTrue(any("POST_LIKE_URL" in g for g in res.failed_gates))

    def test_case_7_candidate_image_unavailable(self):
        """Case 7: Social post URL + candidate image unavailable -> INCONCLUSIVE"""
        cand = DiscoveredCandidate(
            candidate_id="cand_7",
            provider="google_vision",
            page_url="https://www.reddit.com/r/movies/comments/123/craig/",
            image_url="https://i.redd.it/dead.jpg",
            is_social_domain=True,
            is_post_url=True,
            platform="reddit",
            retrieval=self.ret_failed
        )
        ver = VerificationDetails(
            classification=VerificationClassification.UNVERIFIED,
            face_verified=False,
            retrieval=self.ret_failed,
            explanation="Failed to fetch image"
        )
        ctx = {"execution_mode": ExecutionMode.LIVE_EXTERNAL_SEARCH}
        res = evaluate_task3_candidate(cand, ver, ctx)

        self.assertEqual(res.state, Task3ComplianceState.INCONCLUSIVE)
        self.assertFalse(res.passed)
        self.assertTrue(any("EVIDENCE_RETRIEVABLE" in g for g in res.failed_gates))

    def test_case_8_cached_qualifying_result(self):
        """Case 8: Cached qualifying result -> NOT_FINAL_TASK3_PASS"""
        cand = DiscoveredCandidate(
            candidate_id="cand_8",
            provider="google_vision",
            page_url="https://www.reddit.com/r/movies/comments/12345/daniel_craig/",
            is_social_domain=True,
            is_post_url=True,
            platform="reddit",
            retrieval=self.ret_success
        )
        ver = VerificationDetails(
            classification=VerificationClassification.VERIFIED_DERIVATIVE,
            face_verified=True,
            face_similarity=0.9638,
            faces_detected=1,
            retrieval=self.ret_success
        )
        ctx = {"execution_mode": ExecutionMode.CACHE_REPLAY}
        res = evaluate_task3_candidate(cand, ver, ctx)

        self.assertEqual(res.state, Task3ComplianceState.NOT_FINAL_TASK3_PASS)
        self.assertFalse(res.passed)
        self.assertTrue(any("LIVE_EXTERNAL_SEARCH" in g for g in res.failed_gates))

    def test_case_9_mock_qualifying_result(self):
        """Case 9: Mock qualifying result -> TEST_ONLY"""
        cand = DiscoveredCandidate(
            candidate_id="cand_9",
            provider="mock_provider",
            page_url="https://www.reddit.com/r/movies/comments/12345/daniel_craig/",
            is_social_domain=True,
            is_post_url=True,
            platform="reddit",
            retrieval=self.ret_success
        )
        ver = VerificationDetails(
            classification=VerificationClassification.VERIFIED_DERIVATIVE,
            face_verified=True,
            face_similarity=0.9638,
            faces_detected=1,
            retrieval=self.ret_success
        )
        ctx = {"execution_mode": ExecutionMode.MOCK_PROVIDER}
        res = evaluate_task3_candidate(cand, ver, ctx)

        self.assertEqual(res.state, Task3ComplianceState.TEST_ONLY)
        self.assertFalse(res.passed)
        self.assertTrue(any("LIVE_EXTERNAL_SEARCH" in g for g in res.failed_gates))

    def test_case_10_live_qualifying_result(self):
        """Case 10: Live qualifying result -> TASK3_SOCIAL_MATCH"""
        cand = DiscoveredCandidate(
            candidate_id="cand_10",
            provider="google_vision",
            page_url="https://twitter.com/007/status/1234567890",
            is_social_domain=True,
            is_post_url=True,
            platform="x",
            retrieval=self.ret_success
        )
        ver = VerificationDetails(
            classification=VerificationClassification.VERIFIED_DERIVATIVE,
            face_verified=True,
            face_similarity=0.9412,
            faces_detected=1,
            retrieval=self.ret_success
        )
        ctx = {"execution_mode": ExecutionMode.LIVE_EXTERNAL_SEARCH}
        res = evaluate_task3_candidate(cand, ver, ctx)

        self.assertEqual(res.state, Task3ComplianceState.TASK3_SOCIAL_MATCH)
        self.assertTrue(res.passed)


class TestPlatformClassifierEdgeCases(unittest.TestCase):
    """Tests parsed hostname handling, blacklist paths, and social regex rules."""

    def setUp(self):
        self.classifier = PlatformClassifier()

    def test_valid_post_urls(self):
        cases = [
            ("https://www.instagram.com/p/C123abc_-/", "instagram", True),
            ("https://instagram.com/reel/D456def/", "instagram", True),
            ("https://twitter.com/user_12/status/9876543210", "x", True),
            ("https://x.com/user_12/status/9876543210", "x", True),
            ("https://www.reddit.com/r/worldnews/comments/abc12/ukraine_update/", "reddit", True),
            ("https://old.reddit.com/r/pics/comments/xyz99/photo/", "reddit", True),
            ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube", True),
            ("https://youtu.be/dQw4w9WgXcQ", "youtube", True),
            ("https://www.tiktok.com/@creator.official/video/7123456789012345678", "tiktok", True),
            ("https://www.linkedin.com/posts/johndoe_ai-research-activity-123456", "linkedin", True),
            ("https://www.pinterest.com/pin/1234567890/", "pinterest", True),
        ]
        for url, expected_plat, expected_post in cases:
            plat, is_soc, is_post = self.classifier.classify(url)
            self.assertEqual(plat, expected_plat, f"Failed platform for {url}")
            self.assertTrue(is_soc, f"Failed is_social for {url}")
            self.assertEqual(is_post, expected_post, f"Failed is_post for {url}")

    def test_invalid_profile_and_non_post_urls(self):
        non_posts = [
            "https://www.instagram.com/cristiano",
            "https://twitter.com/elonmusk",
            "https://reddit.com/r/pics/",
            "https://www.youtube.com/@mkbhd",
            "https://tiktok.com/@khaby.lame",
            "https://instagram.com/",
            "https://www.facebook.com",
            "https://x.com/login",
            "https://www.instagram.com/accounts/login/",
            "https://reddit.com/search?q=query"
        ]
        for url in non_posts:
            plat, is_soc, is_post = self.classifier.classify(url)
            self.assertFalse(is_post, f"URL should NOT be post: {url}")

    def test_unsafe_substring_domains_rejected(self):
        unrelated = [
            "https://notinstagram.com/p/123",
            "https://fake-twitter.com/user/status/123",
            "https://anti-reddit.org/r/news/comments/123",
            "https://myyoutubeblog.net/watch?v=123"
        ]
        for url in unrelated:
            plat, is_soc, is_post = self.classifier.classify(url)
            self.assertIsNone(plat, f"Unrelated domain should return None: {url}")
            self.assertFalse(is_soc, f"Unrelated domain should not be social: {url}")
            self.assertFalse(is_post, f"Unrelated domain should not be post: {url}")

    def test_uppercase_and_port_handling(self):
        url = "HTTPS://WWW.REDDIT.COM:443/r/movies/comments/abc123/thread/"
        plat, is_soc, is_post = self.classifier.classify(url)
        self.assertEqual(plat, "reddit")
        self.assertTrue(is_soc)
        self.assertTrue(is_post)


if __name__ == "__main__":
    unittest.main()
