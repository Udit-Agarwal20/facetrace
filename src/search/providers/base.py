"""
Abstract Search Provider Interface for Step 2 Reverse Image Search.
Decouples retrieval providers (Google Vision, TinEye, etc.) from the Search Orchestrator.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional

from ..models import MatchClassification


@dataclass
class RawCandidate:
    page_url: str
    image_url: Optional[str] = None
    page_title: Optional[str] = None
    provider_match_type: MatchClassification = MatchClassification.UNKNOWN
    provider_score: float = 0.0
    raw_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderSearchResponse:
    success: bool
    provider_name: str
    candidates: List[RawCandidate] = field(default_factory=list)
    error: Optional[str] = None
    latency_ms: float = 0.0
    query_image_path: Optional[str] = None


class SearchProvider(ABC):
    """Abstract interface that all reverse image search providers must implement."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the provider (e.g., 'google_vision')."""
        pass

    @abstractmethod
    def search(self, image_path: Path) -> ProviderSearchResponse:
        """
        Executes reverse image search for the given image file.
        :param image_path: Path to image to search
        :return: ProviderSearchResponse containing standardized RawCandidate entries.
        """
        pass
