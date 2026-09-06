"""
Search Cache for Query Images.
Caches provider search responses keyed by SHA-256(image_bytes) to avoid redundant API billing.
"""

from pathlib import Path
from typing import List, Optional
import hashlib
import json
import logging
import os

from .providers.base import RawCandidate
from .models import MatchClassification

logger = logging.getLogger(__name__)

DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"


def calculate_image_sha256(image_path: Path) -> str:
    """Calculates SHA-256 hash of the image file bytes."""
    h = hashlib.sha256()
    with open(image_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


class SearchCache:
    """Persistent JSON file cache for search provider outputs."""

    def __init__(self, cache_dir: Optional[Path] = None, enabled: Optional[bool] = None):
        env_dir = os.getenv("SEARCH_CACHE_DIR")
        self.cache_dir = cache_dir or (Path(env_dir) if env_dir else DEFAULT_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        if enabled is not None:
            self.enabled = enabled
        else:
            self.enabled = os.getenv("SEARCH_CACHE_ENABLED", "true").lower() == "true"

    def get(self, image_path: Path, provider_name: str) -> Optional[List[RawCandidate]]:
        """Retrieves cached candidates for an image, if present."""
        if not self.enabled or not image_path.exists():
            return None

        sha = calculate_image_sha256(image_path)
        cache_file = self.cache_dir / f"{provider_name}_{sha}.json"

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            candidates: List[RawCandidate] = []
            for item in data.get("candidates", []):
                candidates.append(RawCandidate(
                    page_url=item.get("page_url", ""),
                    image_url=item.get("image_url"),
                    page_title=item.get("page_title"),
                    provider_match_type=MatchClassification(item.get("provider_match_type", "UNKNOWN")),
                    provider_score=item.get("provider_score", 0.0),
                    raw_metadata=item.get("raw_metadata", {})
                ))

            logger.info(f"[Search Cache] CACHE HIT for {image_path.name} (SHA: {sha[:10]}...). Loaded {len(candidates)} cached results.")
            return candidates
        except Exception as e:
            logger.warning(f"[Search Cache] Failed to read cache file {cache_file}: {e}")
            return None

    def set(self, image_path: Path, provider_name: str, candidates: List[RawCandidate]):
        """Saves search candidates to persistent cache."""
        if not self.enabled or not image_path.exists():
            return

        try:
            sha = calculate_image_sha256(image_path)
            cache_file = self.cache_dir / f"{provider_name}_{sha}.json"

            data = {
                "sha256": sha,
                "provider": provider_name,
                "image_name": image_path.name,
                "candidates": [
                    {
                        "page_url": c.page_url,
                        "image_url": c.image_url,
                        "page_title": c.page_title,
                        "provider_match_type": c.provider_match_type.value,
                        "provider_score": c.provider_score,
                        "raw_metadata": c.raw_metadata
                    }
                    for c in candidates
                ]
            }

            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            logger.info(f"[Search Cache] Cached {len(candidates)} results for {image_path.name} (SHA: {sha[:10]}...).")
        except Exception as e:
            logger.warning(f"[Search Cache] Failed to write cache: {e}")
