"""
Response Normalizer for Search Provider Outputs.
Converts provider-specific candidates into universal internal DiscoveredCandidate objects.
"""

from typing import List, Optional
import hashlib

from .models import DiscoveredCandidate
from .providers.base import RawCandidate
from .platform_classifier import PlatformClassifier


class ResponseNormalizer:
    """Normalizes raw provider candidates into universal domain models."""

    def __init__(self, classifier: Optional[PlatformClassifier] = None):
        self.classifier = classifier or PlatformClassifier()

    def normalize(self, raw_candidates: List[RawCandidate], provider_name: str, query_variant: str) -> List[DiscoveredCandidate]:
        """
        Normalizes a list of raw candidates from a specific query variant.

        :param raw_candidates: Raw candidates from search provider
        :param provider_name: Name of search provider (e.g. 'google_vision')
        :param query_variant: 'original' or 'face_crop'
        :return: List of normalized DiscoveredCandidate objects
        """
        normalized_list: List[DiscoveredCandidate] = []

        for raw in raw_candidates:
            page_url = (raw.page_url or "").strip()
            image_url = (raw.image_url or "").strip() if raw.image_url else None

            # Generate deterministic candidate ID
            id_material = f"{provider_name}:{query_variant}:{page_url}:{image_url or ''}"
            cand_hash = hashlib.sha256(id_material.encode("utf-8")).hexdigest()[:12]
            candidate_id = f"cand_{cand_hash}"

            # Classify social platform & post status
            target_url_for_classification = page_url if page_url else (image_url or "")
            platform_name, is_social, is_post = self.classifier.classify(target_url_for_classification)

            candidate = DiscoveredCandidate(
                candidate_id=candidate_id,
                provider=provider_name,
                query_variants=[query_variant],
                provider_match_type=raw.provider_match_type,
                page_url=page_url,
                image_url=image_url,
                page_title=raw.page_title,
                provider_score=raw.provider_score,
                platform=platform_name,
                is_social_domain=is_social,
                is_post_url=is_post,
                raw_metadata=raw.raw_metadata
            )
            normalized_list.append(candidate)

        return normalized_list
