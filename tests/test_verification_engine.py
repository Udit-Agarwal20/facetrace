"""
Unit & calibration tests for FaceEngine, CandidateRetriever, and FaceVerifier.
"""

import base64
from pathlib import Path
import sys
import unittest
import warnings
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.face_engine import FaceEngine
from src.core.candidate_retriever import CandidateRetriever
from src.core.verifier import FaceVerifier
from src.providers.facecheck_provider import DiscoveredCandidate


class TestVerificationEngine(unittest.TestCase):
    """Encapsulates biometric verification and image preprocessing tests."""

    def test_preprocessing_normal_jpg(self):
        """Tests loading and preprocessing a standard JPEG image."""
        jpg_path = Path("samples/daniel_craig.jpg")
        self.assertTrue(jpg_path.exists(), "Test sample samples/daniel_craig.jpg must exist")

        bgr = FaceEngine.load_image_bgr(jpg_path)
        self.assertIsInstance(bgr, np.ndarray)
        self.assertEqual(bgr.ndim, 3)
        self.assertEqual(bgr.shape[2], 3)
        self.assertEqual(bgr.dtype, np.uint8)
        self.assertTrue(bgr.flags["C_CONTIGUOUS"])
        self.assertGreaterEqual(bgr.min(), 0)
        self.assertLessEqual(bgr.max(), 255)

    def test_preprocessing_palette_transparency(self):
        """Tests loading and preprocessing palette ('P') images with transparency bytes."""
        # Create a synthetic palette image with transparency in memory
        im = Image.new("RGBA", (100, 100), (200, 100, 50, 128))
        pal_im = im.convert("P", palette=Image.ADAPTIVE)

        # Ensure NO UserWarning: Palette images with Transparency expressed in bytes
        with warnings.catch_warnings(record=True) as record:
            warnings.simplefilter("always")
            bgr = FaceEngine.load_image_bgr(pal_im)
            palette_warnings = [
                w for w in record
                if "Palette images with Transparency" in str(w.message)
            ]
            self.assertEqual(len(palette_warnings), 0, f"Palette transparency warning was raised: {palette_warnings}")

        self.assertIsInstance(bgr, np.ndarray)
        self.assertEqual(bgr.ndim, 3)
        self.assertEqual(bgr.shape[2], 3)
        self.assertEqual(bgr.dtype, np.uint8)
        self.assertTrue(bgr.flags["C_CONTIGUOUS"])
        self.assertGreater(bgr.max(), 0, "Image should not be completely blank")

    def test_positive_and_negative_similarity_calibration(self):
        engine = FaceEngine(model_name="buffalo_sc")
        verifier = FaceVerifier(threshold=0.60, inconclusive_lower_bound=0.40)

        # 1. Query image
        query_res = engine.detect_and_embed(Path("samples/daniel_craig.jpg"))
        self.assertTrue(query_res.detected)
        self.assertIsNotNone(query_res.embedding)
        self.assertEqual(len(query_res.embedding), 512)

        # 2. Positive candidate (same person, mirrored orientation)
        pos_res = engine.detect_and_embed(Path("samples/daniel_craig_flipped.jpg"))
        self.assertTrue(pos_res.detected)
        self.assertIsNotNone(pos_res.embedding)

        pos_decision = verifier.evaluate(
            query_embedding=query_res.embedding,
            candidate_embedding=pos_res.embedding,
            candidate_id="cand_pos",
            source_url="https://example.com/positive_sample",
            candidate_detection_score=pos_res.detection_score,
            provider_score=92
        )

        self.assertGreaterEqual(pos_decision.similarity, 0.70)
        self.assertEqual(pos_decision.decision, "ACCEPTED")

        # 3. Negative candidate (different person: InsightFace t1 sample)
        neg_res = engine.detect_and_embed(Path("samples/t1_person.jpg"))
        self.assertTrue(neg_res.detected)
        self.assertIsNotNone(neg_res.embedding)

        neg_decision = verifier.evaluate(
            query_embedding=query_res.embedding,
            candidate_embedding=neg_res.embedding,
            candidate_id="cand_neg",
            source_url="https://example.com/negative_sample",
            candidate_detection_score=neg_res.detection_score,
            provider_score=20
        )

        self.assertLess(neg_decision.similarity, 0.40)
        self.assertEqual(neg_decision.decision, "REJECTED")

    def test_candidate_retriever_base64(self):
        retriever = CandidateRetriever()

        # Create dummy base64 thumbnail from real sample
        with open("samples/daniel_craig.jpg", "rb") as f:
            raw_bytes = f.read()
        b64_str = "data:image/jpeg;base64," + base64.b64encode(raw_bytes).decode("utf-8")

        candidate = DiscoveredCandidate(
            candidate_id="cand_test_b64",
            source_url="https://example.com/test",
            provider_score=85,
            thumbnail_base64=b64_str
        )

        res = retriever.retrieve_candidate(candidate)
        self.assertEqual(res.status, "RETRIEVED")
        self.assertIsNotNone(res.pil_image)
        self.assertIsNotNone(res.image_bytes)

    def test_candidate_external_url_validation(self):
        """Validates that candidate source URLs must be genuine external pages, not facecheck.id placeholders."""
        # Internal placeholders
        cand_internal_1 = DiscoveredCandidate(
            candidate_id="cand_int1",
            source_url="https://facecheck.id",
            provider_score=90
        )
        cand_internal_2 = DiscoveredCandidate(
            candidate_id="cand_int2",
            source_url="https://www.facecheck.id/some/placeholder",
            provider_score=85
        )
        self.assertFalse(cand_internal_1.is_external_source())
        self.assertFalse(cand_internal_2.is_external_source())

        # External genuine web pages
        cand_ext_1 = DiscoveredCandidate(
            candidate_id="cand_ext1",
            source_url="https://www.instagram.com/p/C_abc123/",
            provider_score=88
        )
        cand_ext_2 = DiscoveredCandidate(
            candidate_id="cand_ext2",
            source_url="https://www.imdb.com/name/nm0185819/",
            provider_score=94
        )
        self.assertTrue(cand_ext_1.is_external_source())
        self.assertTrue(cand_ext_2.is_external_source())


if __name__ == "__main__":
    unittest.main()
