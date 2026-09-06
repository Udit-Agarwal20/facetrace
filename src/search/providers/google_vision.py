"""
Google Cloud Vision Web Detection Provider Adapter.
Implements reverse image retrieval via Google Vision API with retry policy and Page -> Image association.
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import logging
import os
import time

# Ensure reliable DNS resolution across macOS network stacks
os.environ.setdefault("GRPC_DNS_RESOLVER", "native")

from .base import SearchProvider, ProviderSearchResponse, RawCandidate
from ..models import MatchClassification

logger = logging.getLogger(__name__)


class GoogleVisionProvider(SearchProvider):
    """Adapter for Google Cloud Vision Web Detection API."""

    def __init__(self, credentials_path: Optional[str] = None, max_retries: int = 3):
        self._credentials_path = credentials_path
        self._max_retries = max_retries
        self._client = None

    @property
    def name(self) -> str:
        return "google_vision"

    def _get_client(self):
        if self._client is None:
            try:
                from google.cloud import vision
                if self._credentials_path:
                    self._client = vision.ImageAnnotatorClient.from_service_account_json(self._credentials_path)
                else:
                    # Uses Application Default Credentials (ADC)
                    self._client = vision.ImageAnnotatorClient()
                logger.info("Initialized Google Cloud Vision ImageAnnotatorClient.")
            except Exception as e:
                logger.error(f"Failed to initialize Google Cloud Vision client: {e}")
                raise RuntimeError(f"Google Cloud Vision initialization failed: {e}") from e
        return self._client

    def search(self, image_path: Path) -> ProviderSearchResponse:
        """
        Executes Google Cloud Vision Web Detection on the input image.
        """
        if not image_path.exists():
            return ProviderSearchResponse(
                success=False,
                provider_name=self.name,
                error=f"Image file does not exist: {image_path}",
                query_image_path=str(image_path)
            )

        client = self._get_client()
        from google.cloud import vision
        from google.api_core.exceptions import GoogleAPICallError, RetryError, TooManyRequests, ServiceUnavailable

        with open(image_path, "rb") as f:
            content = f.read()

        image = vision.Image(content=content)
        start_time = time.time()

        # Retry loop with exponential backoff for transient errors
        last_error = None
        for attempt in range(1, self._max_retries + 1):
            try:
                logger.info(f"[Google Vision] Submitting Web Detection request for {image_path.name} (attempt {attempt}/{self._max_retries})...")
                response = client.web_detection(image=image, timeout=20.0)

                if response.error.message:
                    return ProviderSearchResponse(
                        success=False,
                        provider_name=self.name,
                        error=f"Google Vision API Error: {response.error.message}",
                        latency_ms=(time.time() - start_time) * 1000,
                        query_image_path=str(image_path)
                    )

                latency = (time.time() - start_time) * 1000
                web_detection = response.web_detection
                candidates = self._parse_web_detection(web_detection)

                logger.info(f"[Google Vision] Succeeded in {latency:.0f}ms. Discovered {len(candidates)} raw candidates.")
                return ProviderSearchResponse(
                    success=True,
                    provider_name=self.name,
                    candidates=candidates,
                    latency_ms=latency,
                    query_image_path=str(image_path)
                )

            except (TooManyRequests, ServiceUnavailable, GoogleAPICallError, TimeoutError) as e:
                last_error = e
                backoff = 0.5 * (2 ** (attempt - 1))
                logger.warning(f"[Google Vision] Transient error on attempt {attempt}: {e}. Retrying in {backoff:.1f}s...")
                time.sleep(backoff)
            except Exception as e:
                logger.error(f"[Google Vision] Non-retryable error: {e}")
                return ProviderSearchResponse(
                    success=False,
                    provider_name=self.name,
                    error=f"Google Vision unexpected error: {str(e)}",
                    latency_ms=(time.time() - start_time) * 1000,
                    query_image_path=str(image_path)
                )

        return ProviderSearchResponse(
            success=False,
            provider_name=self.name,
            error=f"Google Vision failed after {self._max_retries} attempts: {last_error}",
            latency_ms=(time.time() - start_time) * 1000,
            query_image_path=str(image_path)
        )

    def _parse_web_detection(self, web_detection) -> List[RawCandidate]:
        """
        Parses Google WebDetection object, preserving Page -> Image relationships.
        """
        candidates: List[RawCandidate] = []
        seen_pairs = set()

        if not web_detection:
            return candidates

        # 1. Parse pages_with_matching_images (Strongest relationship: Page contains specific matching image)
        for page in getattr(web_detection, "pages_with_matching_images", []):
            page_url = getattr(page, "url", "")
            page_title = getattr(page, "page_title", None)

            # Check full matching images inside this page
            page_full_imgs = getattr(page, "full_matching_images", [])
            for img in page_full_imgs:
                img_url = getattr(img, "url", None)
                pair = (page_url, img_url)
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    candidates.append(RawCandidate(
                        page_url=page_url,
                        image_url=img_url,
                        page_title=page_title,
                        provider_match_type=MatchClassification.FULL,
                        provider_score=0.95,
                        raw_metadata={"relationship": "page_with_full_matching_image"}
                    ))

            # Check partial matching images inside this page
            page_part_imgs = getattr(page, "partial_matching_images", [])
            for img in page_part_imgs:
                img_url = getattr(img, "url", None)
                pair = (page_url, img_url)
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    candidates.append(RawCandidate(
                        page_url=page_url,
                        image_url=img_url,
                        page_title=page_title,
                        provider_match_type=MatchClassification.PARTIAL,
                        provider_score=0.85,
                        raw_metadata={"relationship": "page_with_partial_matching_image"}
                    ))

            # If page was returned without nested image objects
            if not page_full_imgs and not page_part_imgs:
                pair = (page_url, None)
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    candidates.append(RawCandidate(
                        page_url=page_url,
                        image_url=None,
                        page_title=page_title,
                        provider_match_type=MatchClassification.FULL,
                        provider_score=0.80,
                        raw_metadata={"relationship": "page_unspecified_match"}
                    ))

        # 2. Parse top-level full_matching_images (Direct image URLs)
        for img in getattr(web_detection, "full_matching_images", []):
            img_url = getattr(img, "url", None)
            if img_url:
                pair = ("", img_url)
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    candidates.append(RawCandidate(
                        page_url="",
                        image_url=img_url,
                        provider_match_type=MatchClassification.FULL,
                        provider_score=0.90,
                        raw_metadata={"relationship": "direct_full_image"}
                    ))

        # 3. Parse top-level partial_matching_images
        for img in getattr(web_detection, "partial_matching_images", []):
            img_url = getattr(img, "url", None)
            if img_url:
                pair = ("", img_url)
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    candidates.append(RawCandidate(
                        page_url="",
                        image_url=img_url,
                        provider_match_type=MatchClassification.PARTIAL,
                        provider_score=0.75,
                        raw_metadata={"relationship": "direct_partial_image"}
                    ))

        # 4. Parse visually_similar_images (Stricter scrutiny)
        for img in getattr(web_detection, "visually_similar_images", []):
            img_url = getattr(img, "url", None)
            if img_url:
                pair = ("", img_url)
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    candidates.append(RawCandidate(
                        page_url="",
                        image_url=img_url,
                        provider_match_type=MatchClassification.SIMILAR,
                        provider_score=0.50,
                        raw_metadata={"relationship": "visually_similar_image"}
                    ))

        return candidates
