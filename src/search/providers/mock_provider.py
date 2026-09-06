"""
Deterministic Mock Search Provider for Unit Tests and Offline Validation.
"""

from pathlib import Path
from typing import List, Optional

from .base import SearchProvider, ProviderSearchResponse, RawCandidate
from ..models import MatchClassification


class MockSearchProvider(SearchProvider):
    """Configurable mock provider returning predefined candidate sets."""

    def __init__(self, predefined_candidates: Optional[List[RawCandidate]] = None, name: str = "mock_provider"):
        self._name = name
        self._candidates = predefined_candidates if predefined_candidates is not None else [
            RawCandidate(
                page_url="https://www.reddit.com/r/movies/comments/12345/daniel_craig_photo/",
                image_url="https://i.redd.it/example_craig.jpg",
                page_title="Daniel Craig discussion thread",
                provider_match_type=MatchClassification.FULL,
                provider_score=0.95
            ),
            RawCandidate(
                page_url="https://www.instagram.com/p/C_abc12345/",
                image_url="https://instagram.fsan1-1.fna.fbcdn.net/example.jpg",
                page_title="Instagram post",
                provider_match_type=MatchClassification.PARTIAL,
                provider_score=0.85
            ),
            RawCandidate(
                page_url="https://en.wikipedia.org/wiki/Daniel_Craig",
                image_url="https://upload.wikimedia.org/wikipedia/commons/example.jpg",
                page_title="Daniel Craig - Wikipedia",
                provider_match_type=MatchClassification.FULL,
                provider_score=0.92
            ),
            RawCandidate(
                page_url="https://example.com/unrelated/page",
                image_url="https://example.com/similar.jpg",
                page_title="Unrelated",
                provider_match_type=MatchClassification.SIMILAR,
                provider_score=0.45
            )
        ]

    @property
    def name(self) -> str:
        return self._name

    def search(self, image_path: Path) -> ProviderSearchResponse:
        return ProviderSearchResponse(
            success=True,
            provider_name=self.name,
            candidates=list(self._candidates),
            latency_ms=45.0,
            query_image_path=str(image_path)
        )
