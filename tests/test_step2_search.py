"""
Comprehensive unit and integration test suite for Step 2 Search Subsystem.
Tests query variant generation, URL canonicalization, platform classification,
candidate ranking, multi-level verification ladder, and end-to-end orchestrator execution.
"""

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.search.models import (
    SearchRequest,
    FaceInfo,
    FaceBoundingBox,
    MatchClassification,
    DiscoveredCandidate,
    VerificationClassification,
    RetrievalDetails
)
from src.search.query_variants import QueryVariantGenerator
from src.search.deduplicator import canonicalize_url, CandidateDeduplicator
from src.search.platform_classifier import PlatformClassifier
from src.search.ranker import CandidateRanker
from src.search.verifier import MultiLevelVerifier
from src.search.providers.mock_provider import MockSearchProvider
from src.search.orchestrator import SearchOrchestrator


class TestStep2SearchSubsystem(unittest.TestCase):
    """Encapsulates Step 2 tests for standard discovery via unittest."""

    def test_query_variant_generation(self):
        img_path = Path("samples/daniel_craig.jpg")
        self.assertTrue(img_path.exists())

        gen = QueryVariantGenerator(padding_ratio=0.25)
        bbox = FaceBoundingBox(x=80.0, y=23.0, width=100.0, height=126.0)

        variants = gen.generate(img_path, bbox, job_id="test_job")

        self.assertTrue(variants.original_path.exists())
        self.assertTrue(variants.face_crop_path.exists())
        self.assertEqual(variants.original_path, img_path.resolve())

        # Check crop dimensions are padded
        with Image.open(variants.face_crop_path) as crop_im:
            w, h = crop_im.size
            self.assertGreater(w, 100)
            self.assertGreater(h, 126)

        # Test cleanup
        crop_file = variants.face_crop_path
        variants.cleanup()
        self.assertFalse(crop_file.exists())

    def test_url_canonicalization_and_deduplication(self):
        url1 = "https://reddit.com/r/movies/comments/123/craig/?utm_source=twitter&utm_medium=social#comments"
        url2 = "https://reddit.com/r/movies/comments/123/craig"

        canon1 = canonicalize_url(url1)
        canon2 = canonicalize_url(url2)
        self.assertEqual(canon1, canon2)
        self.assertNotIn("utm_source", canon1)
        self.assertNotIn("#comments", canon1)

        # Test candidate deduplication and dual-query merging
        cand_a = DiscoveredCandidate(
            candidate_id="cand_a",
            provider="mock",
            query_variants=["original"],
            provider_match_type=MatchClassification.FULL,
            page_url=url1,
            image_url="https://i.redd.it/test.jpg"
        )
        cand_b = DiscoveredCandidate(
            candidate_id="cand_b",
            provider="mock",
            query_variants=["face_crop"],
            provider_match_type=MatchClassification.PARTIAL,
            page_url=url2,
            image_url="https://i.redd.it/test.jpg"
        )

        dedup = CandidateDeduplicator()
        merged = dedup.deduplicate([cand_a, cand_b])

        self.assertEqual(len(merged), 1)
        self.assertIn("original", merged[0].query_variants)
        self.assertIn("face_crop", merged[0].query_variants)
        self.assertEqual(merged[0].provider_match_type, MatchClassification.FULL)

    def test_platform_classification(self):
        classifier = PlatformClassifier()

        # Instagram post vs root
        p1, s1, post1 = classifier.classify("https://www.instagram.com/p/DA_12345/?igsh=abc")
        self.assertEqual(p1, "instagram")
        self.assertTrue(s1)
        self.assertTrue(post1)

        p2, s2, post2 = classifier.classify("https://instagram.com/explore")
        self.assertEqual(p2, "instagram")
        self.assertTrue(s2)
        self.assertFalse(post2)

        # Reddit comments
        p3, s3, post3 = classifier.classify("https://reddit.com/r/technology/comments/xyz123/article/")
        self.assertEqual(p3, "reddit")
        self.assertTrue(s3)
        self.assertTrue(post3)

        # X / Twitter status
        p4, s4, post4 = classifier.classify("https://twitter.com/user/status/123456789")
        self.assertEqual(p4, "x")
        self.assertTrue(s4)
        self.assertTrue(post4)

        # Generic website
        p5, s5, post5 = classifier.classify("https://en.wikipedia.org/wiki/Daniel_Craig")
        self.assertIsNone(p5)
        self.assertFalse(s5)
        self.assertFalse(post5)

    def test_candidate_ranker(self):
        ranker = CandidateRanker()

        c_social_post = DiscoveredCandidate(
            candidate_id="c1",
            provider="mock",
            query_variants=["original", "face_crop"],  # dual query bonus
            provider_match_type=MatchClassification.FULL,
            page_url="https://reddit.com/r/test/comments/123/",
            image_url="https://i.redd.it/img.jpg",
            is_social_domain=True,
            is_post_url=True,
            provider_score=0.90
        )

        c_generic = DiscoveredCandidate(
            candidate_id="c2",
            provider="mock",
            query_variants=["original"],
            provider_match_type=MatchClassification.PARTIAL,
            page_url="https://example.com/page",
            image_url=None,
            is_social_domain=False,
            is_post_url=False,
            provider_score=0.50
        )

        ranked = ranker.rank([c_generic, c_social_post])
        self.assertEqual(ranked[0].candidate_id, "c1")
        self.assertGreater(ranked[0].retrieval_score, ranked[1].retrieval_score)

    def test_multi_level_verifier_exact_and_phash(self):
        verifier = MultiLevelVerifier()
        img_path = Path("samples/daniel_craig.jpg")

        dummy_face = FaceInfo(
            bbox=FaceBoundingBox(x=0, y=0, width=10, height=10),
            embedding=[0.1] * 512
        )

        ret_ok = RetrievalDetails(source_reachable=True, evidence_retrieved=True, image_valid=True)

        # 1. Level 1: Exact byte match
        cand_exact = DiscoveredCandidate(
            candidate_id="cand_exact",
            provider="mock",
            image_url=str(img_path.resolve())
        )
        with open(img_path, "rb") as f:
            cand_bytes = f.read()
        verifier.fetch_candidate_image = lambda c: (cand_bytes, Image.open(io.BytesIO(cand_bytes)), ret_ok)

        ver_exact = verifier.verify(cand_exact, img_path, dummy_face)
        self.assertEqual(ver_exact.classification, VerificationClassification.VERIFIED_EXACT)
        self.assertTrue(ver_exact.sha256_exact)
        self.assertEqual(ver_exact.phash_distance, 0)

        # 2. Level 2: Perceptual hash derivative match (resized/recompressed image)
        with open(img_path, "rb") as f:
            orig_bytes = f.read()
        orig_pil = Image.open(io.BytesIO(orig_bytes))
        resized_pil = orig_pil.resize((int(orig_pil.width * 0.8), int(orig_pil.height * 0.8)))
        buf = io.BytesIO()
        resized_pil.save(buf, format="JPEG", quality=75)
        deriv_bytes = buf.getvalue()
        buf.seek(0)
        deriv_pil = Image.open(buf)
        verifier.fetch_candidate_image = lambda c: (deriv_bytes, deriv_pil, ret_ok)

        ver_deriv = verifier.verify(cand_exact, img_path, dummy_face)
        self.assertEqual(ver_deriv.classification, VerificationClassification.VERIFIED_DERIVATIVE)
        self.assertFalse(ver_deriv.sha256_exact)
        self.assertIsNotNone(ver_deriv.phash_distance)
        self.assertLessEqual(ver_deriv.phash_distance, 10)

    def test_orchestrator_mock_end_to_end(self):
        img_path = Path("samples/daniel_craig.jpg")
        mock_provider = MockSearchProvider()
        orchestrator = SearchOrchestrator(
            provider=mock_provider,
            max_verification_candidates=5
        )

        req = SearchRequest(
            job_id="test_scan_001",
            original_image=str(img_path),
            face=FaceInfo(
                bbox=FaceBoundingBox(x=80.0, y=23.0, width=100.0, height=126.0),
                embedding=[0.05] * 512
            )
        )
        with open(img_path, "rb") as f:
            mock_bytes = f.read()
        mock_pil = Image.open(io.BytesIO(mock_bytes))
        ret_ok = RetrievalDetails(source_reachable=True, evidence_retrieved=True, image_valid=True)
        orchestrator.verifier.fetch_candidate_image = lambda c: (mock_bytes, mock_pil, ret_ok)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=True) as tmp:
            output_file = Path(tmp.name)
            result = orchestrator.search(req, output_path=output_file)

            self.assertEqual(result.job_id, "test_scan_001")
            self.assertIn(result.status, ("SOCIAL_POST_MATCH_FOUND", "MATCH_FOUND", "WEB_MATCH_FOUND"))
            self.assertGreater(result.metrics["raw_candidate_count"], 0)
            self.assertGreater(result.metrics["deduplicated_count"], 0)
            self.assertGreater(len(result.all_candidates), 0)

            self.assertTrue(output_file.exists())
            with open(output_file, "r") as f:
                saved = json.load(f)
            self.assertEqual(saved["job_id"], "test_scan_001")
            self.assertEqual(saved.get("schema_version"), "1.0")
            self.assertIn("task3_compliance", saved)
            self.assertIn("provenance", saved)
            self.assertIn("search", saved)


if __name__ == "__main__":
    unittest.main()
