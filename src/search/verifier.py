"""
Multi-Level Candidate Verification Engine.
Implements Verification Ladder:
Level 1: SHA-256 exact binary hash
Level 2: Perceptual Hash (pHash distance via imagehash)
Level 3: ArcFace biometric verification with multi-face candidate support.
"""

from pathlib import Path
from typing import Optional, List, Tuple
import hashlib
import io
import logging
from PIL import Image
import numpy as np
import requests

from .models import (
    DiscoveredCandidate,
    VerificationDetails,
    VerificationClassification,
    MatchClassification,
    FaceInfo,
    RetrievalDetails
)
from ..core.face_engine import FaceEngine

logger = logging.getLogger(__name__)


def compute_bytes_sha256(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


class MultiLevelVerifier:
    """
    Evaluates discovered candidates across a multi-tiered verification ladder:
    1. SHA-256 byte identity
    2. Perceptual image hashing (pHash) - perceptual visual similarity
    3. Biometric ArcFace face verification (with multi-face candidate support)
    """

    def __init__(
        self,
        face_engine: Optional[FaceEngine] = None,
        face_threshold: float = 0.72,
        phash_max_derivative_distance: int = 10,
        timeout_seconds: int = 15
    ):
        self.face_engine = face_engine or FaceEngine(model_name="buffalo_sc")
        self.face_threshold = face_threshold
        self.phash_max_derivative_distance = phash_max_derivative_distance
        self.timeout = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        })

    def fetch_candidate_image(self, candidate: DiscoveredCandidate) -> Tuple[Optional[bytes], Optional[Image.Image], RetrievalDetails]:
        """
        Retrieves candidate image from image_url or page_url.
        Returns: (image_bytes, pil_image, retrieval_details)
        """
        source_reachable = False
        evidence_retrieved = False
        image_valid = False
        error_msg = None

        urls_to_try = []
        if candidate.image_url:
            urls_to_try.append(candidate.image_url)
        # Only try page_url if it ends with an image extension
        if candidate.page_url and candidate.page_url.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
            if candidate.page_url not in urls_to_try:
                urls_to_try.append(candidate.page_url)

        # If no direct image URL is known, attempt OpenGraph / Twitter meta image resolution from page
        if not urls_to_try and candidate.page_url and candidate.page_url.startswith(("http://", "https://")):
            try:
                page_resp = self.session.get(candidate.page_url, timeout=5, allow_redirects=True)
                if page_resp.status_code == 200:
                    source_reachable = True
                    if "text/html" in page_resp.headers.get("Content-Type", ""):
                        import re
                        og_match = re.search(r'<meta[^>]+property=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)["\']', page_resp.text, re.IGNORECASE) or \
                                   re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\'](?:og:image|twitter:image)["\']', page_resp.text, re.IGNORECASE) or \
                                   re.search(r'<meta[^>]+name=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)["\']', page_resp.text, re.IGNORECASE)
                        if og_match:
                            import html
                            extracted_img = html.unescape(og_match.group(1).strip())
                            if extracted_img.startswith("//"):
                                extracted_img = "https:" + extracted_img
                            elif extracted_img.startswith("/"):
                                from urllib.parse import urljoin
                                extracted_img = urljoin(candidate.page_url, extracted_img)
                            urls_to_try.append(extracted_img)
                            candidate.image_url = extracted_img
                            logger.info(f"[Verifier] Extracted OpenGraph image for {candidate.page_url}: {extracted_img}")
                else:
                    error_msg = f"Candidate page returned HTTP {page_resp.status_code}"
            except Exception as e:
                error_msg = f"Failed to access candidate page: {e}"
                logger.debug(f"OpenGraph extraction failed for {candidate.page_url}: {e}")

        if not urls_to_try:
            retrieval = RetrievalDetails(
                source_reachable=source_reachable,
                evidence_retrieved=False,
                image_valid=False,
                error=error_msg or "No direct image URL or OpenGraph image found for candidate."
            )
            return None, None, retrieval

        for target_url in urls_to_try:
            try:
                resp = self.session.get(target_url, timeout=self.timeout)
                if resp.status_code == 200:
                    source_reachable = True
                    evidence_retrieved = True
                    raw_bytes = resp.content
                    try:
                        pil_img = Image.open(io.BytesIO(raw_bytes))
                        pil_img.verify()
                        # Re-open after verify
                        pil_img = Image.open(io.BytesIO(raw_bytes))
                        image_valid = True
                        retrieval = RetrievalDetails(
                            source_reachable=True,
                            evidence_retrieved=True,
                            image_valid=True,
                            error=None
                        )
                        return raw_bytes, pil_img, retrieval
                    except Exception as img_err:
                        error_msg = f"Downloaded content is not a decodable image: {img_err}"
                        logger.debug(f"Image decode failed for {target_url}: {img_err}")
                else:
                    error_msg = f"HTTP {resp.status_code} fetching image from {target_url}"
            except Exception as e:
                error_msg = f"Network exception fetching candidate image from {target_url}: {e}"
                logger.debug(f"Failed to fetch candidate image from {target_url}: {e}")

        retrieval = RetrievalDetails(
            source_reachable=source_reachable,
            evidence_retrieved=evidence_retrieved,
            image_valid=image_valid,
            error=error_msg or f"Failed to retrieve candidate image from URLs: {urls_to_try}"
        )
        return None, None, retrieval

    def verify(
        self,
        candidate: DiscoveredCandidate,
        original_image_path: Path,
        query_face: FaceInfo
    ) -> VerificationDetails:
        """
        Runs candidate through the verification ladder.
        """
        # Read original query image
        with open(original_image_path, "rb") as f:
            query_bytes = f.read()
        query_sha256 = compute_bytes_sha256(query_bytes)
        query_pil = Image.open(io.BytesIO(query_bytes))

        # Fetch candidate image
        cand_bytes, cand_pil, retrieval_details = self.fetch_candidate_image(candidate)
        candidate.retrieval = retrieval_details

        if cand_bytes is None or cand_pil is None:
            return VerificationDetails(
                classification=VerificationClassification.UNVERIFIED,
                sha256_exact=False,
                face_verified=False,
                retrieval=retrieval_details,
                explanation=f"Candidate image unreachable: {retrieval_details.error or 'Failed to fetch'}"
            )

        # ----------------------------------------------------------------------
        # LEVEL 1: Exact Binary Hash (SHA-256)
        # ----------------------------------------------------------------------
        cand_sha256 = compute_bytes_sha256(cand_bytes)
        sha256_exact = (query_sha256 == cand_sha256)

        if sha256_exact:
            logger.info(f"[Verifier] Candidate {candidate.candidate_id}: LEVEL 1 MATCH (Exact SHA-256 byte identity).")
            return VerificationDetails(
                classification=VerificationClassification.VERIFIED_EXACT,
                sha256_exact=True,
                sha256_candidate=cand_sha256,
                phash_distance=0,
                face_verified=True,
                face_similarity=1.0,
                faces_detected=1,
                best_face_index=0,
                retrieval=retrieval_details,
                explanation="Byte-exact match: Candidate image SHA-256 is identical to query image."
            )

        # ----------------------------------------------------------------------
        # LEVEL 2: Perceptual Hash (pHash)
        # ----------------------------------------------------------------------
        phash_distance = None
        try:
            import imagehash
            # Ensure RGB before computing pHash
            q_rgb = query_pil.convert("RGB")
            c_rgb = cand_pil.convert("RGB")
            h_query = imagehash.phash(q_rgb)
            h_cand = imagehash.phash(c_rgb)
            phash_distance = int(h_query - h_cand)
            logger.info(f"[Verifier] Candidate {candidate.candidate_id}: pHash distance = {phash_distance}")
        except Exception as e:
            logger.warning(f"pHash calculation failed: {e}")

        # ----------------------------------------------------------------------
        # LEVEL 3: Biometric ArcFace Face Verification (with Multi-Face Support)
        # ----------------------------------------------------------------------
        face_verified = False
        face_similarity = None
        faces_detected = 0
        best_face_index = None

        if query_face.embedding is not None:
            try:
                self.face_engine._ensure_initialized()
                c_bgr = self.face_engine.load_image_bgr(cand_pil)
                detected_faces = self.face_engine._app.get(c_bgr)
                faces_detected = len(detected_faces)

                if faces_detected > 0:
                    q_emb = np.asarray(query_face.embedding, dtype=np.float32).flatten()
                    q_norm = np.linalg.norm(q_emb)
                    if q_norm > 0:
                        q_emb = q_emb / q_norm

                    best_sim = -1.0
                    for idx, f in enumerate(detected_faces):
                        c_emb = f.embedding
                        if c_emb is not None:
                            c_emb = np.asarray(c_emb, dtype=np.float32).flatten()
                            c_norm = np.linalg.norm(c_emb)
                            if c_norm > 0:
                                c_emb = c_emb / c_norm
                            sim = float(np.dot(q_emb, c_emb))
                            if sim > best_sim:
                                best_sim = sim
                                best_face_index = idx

                    if best_sim >= -1.0:
                        face_similarity = round(best_sim, 4)
                        if face_similarity >= self.face_threshold:
                            face_verified = True

                logger.info(
                    f"[Verifier] Candidate {candidate.candidate_id}: Face verification: "
                    f"faces={faces_detected}, best_sim={face_similarity}, verified={face_verified}"
                )
            except Exception as e:
                logger.warning(f"Face verification failed on candidate: {e}")

        # ----------------------------------------------------------------------
        # CONFIDENCE CLASSIFICATION DECISION
        # ----------------------------------------------------------------------
        # 1. VERIFIED_DERIVATIVE: Strong perceptual similarity OR (good pHash + verified face)
        if phash_distance is not None and phash_distance <= self.phash_max_derivative_distance:
            classification = VerificationClassification.VERIFIED_DERIVATIVE
            explanation = (
                f"Derivative match: Perceptual hash distance ({phash_distance}) within threshold ({self.phash_max_derivative_distance}). "
                f"Image is a legitimate resize, recompression, or minor crop of query image."
            )
        elif face_verified:
            classification = VerificationClassification.VERIFIED_DERIVATIVE
            explanation = (
                f"Biometric derivative match: Candidate face independently verified "
                f"(similarity {face_similarity:.4f} >= threshold {self.face_threshold:.2f}, {faces_detected} face(s) in candidate)."
            )
        elif phash_distance is not None and phash_distance <= 16:
            classification = VerificationClassification.PROBABLE_MATCH
            explanation = f"Probable match: pHash distance ({phash_distance}) indicates high visual similarity."
        elif face_similarity is not None and face_similarity >= 0.55:
            classification = VerificationClassification.PROBABLE_MATCH
            explanation = f"Probable match: Candidate face similarity ({face_similarity:.4f}) shows moderate correlation."
        elif phash_distance is not None and phash_distance > 20 and (face_similarity is not None and face_similarity < 0.40):
            classification = VerificationClassification.REJECTED
            explanation = f"Rejected: High pHash distance ({phash_distance}) and low face similarity ({face_similarity:.4f})."
        else:
            classification = VerificationClassification.UNVERIFIED
            explanation = f"Unverified: Candidate image does not meet derivative or biometric confidence gates."

        return VerificationDetails(
            classification=classification,
            sha256_exact=False,
            sha256_candidate=cand_sha256,
            phash_distance=phash_distance,
            face_verified=face_verified,
            face_similarity=face_similarity,
            faces_detected=faces_detected,
            best_face_index=best_face_index,
            retrieval=retrieval_details,
            explanation=explanation
        )
