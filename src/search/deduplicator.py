"""
Deduplication Engine and URL Canonicalizer for Search Candidates.
Aggregates candidates from dual query variants, canonicalizes URLs, and merges duplicates.
"""

from typing import List, Dict, Tuple
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
import logging

from .models import DiscoveredCandidate, MatchClassification

logger = logging.getLogger(__name__)

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "source", "igshid", "t", "s", "feature"
}

MATCH_PRIORITY = {
    MatchClassification.EXACT: 4,
    MatchClassification.FULL: 3,
    MatchClassification.PARTIAL: 2,
    MatchClassification.SIMILAR: 1,
    MatchClassification.UNKNOWN: 0
}


def canonicalize_url(raw_url: str) -> str:
    """
    Canonicalizes a URL by:
    - Normalizing scheme and netloc to lowercase
    - Stripping fragment (#...)
    - Stripping common tracking parameters (utm_*, fbclid, etc.)
    - Removing trailing slashes (except root)
    """
    if not raw_url:
        return ""

    try:
        parsed = urlparse(raw_url.strip())
        if not parsed.netloc:
            return raw_url.strip()

        scheme = parsed.scheme.lower() or "https"
        netloc = parsed.netloc.lower()

        # Normalize path: strip trailing slash if not root
        path = parsed.path
        if len(path) > 1 and path.endswith("/"):
            path = path.rstrip("/")

        # Filter query parameters
        filtered_query = []
        if parsed.query:
            for k, v in parse_qsl(parsed.query, keep_blank_values=False):
                if k.lower() not in TRACKING_PARAMS:
                    filtered_query.append((k, v))

        query_str = urlencode(filtered_query)
        clean_parsed = (scheme, netloc, path, parsed.params, query_str, "")
        return urlunparse(clean_parsed)
    except Exception as e:
        logger.debug(f"Error canonicalizing URL '{raw_url}': {e}")
        return raw_url.strip()


class CandidateDeduplicator:
    """Merges and deduplicates candidates across multiple query variants."""

    def deduplicate(self, candidates: List[DiscoveredCandidate]) -> List[DiscoveredCandidate]:
        """
        Deduplicates candidate pool. Merges candidates found in multiple query variants.
        """
        merged_map: Dict[Tuple[str, str], DiscoveredCandidate] = {}

        for cand in candidates:
            clean_page = canonicalize_url(cand.page_url)
            clean_image = canonicalize_url(cand.image_url or "")

            # Group key: (canonical_page_url, canonical_image_url)
            # If image_url is missing, key on page_url alone
            key = (clean_page, clean_image)

            if key not in merged_map:
                # Store copy with canonicalized URLs
                cand.page_url = clean_page
                cand.image_url = clean_image if clean_image else None
                merged_map[key] = cand
            else:
                existing = merged_map[key]
                # Merge query_variants (e.g. ['original', 'face_crop'])
                for qv in cand.query_variants:
                    if qv not in existing.query_variants:
                        existing.query_variants.append(qv)

                # Prioritize higher match type
                if MATCH_PRIORITY.get(cand.provider_match_type, 0) > MATCH_PRIORITY.get(existing.provider_match_type, 0):
                    existing.provider_match_type = cand.provider_match_type

                # Take highest provider score
                existing.provider_score = max(existing.provider_score, cand.provider_score)

                # If existing lacked image_url, fill it
                if not existing.image_url and clean_image:
                    existing.image_url = clean_image

                # If existing lacked page_title, fill it
                if not existing.page_title and cand.page_title:
                    existing.page_title = cand.page_title

        result = list(merged_map.values())
        logger.info(f"[Deduplicator] Input: {len(candidates)} candidates -> Deduplicated: {len(result)} candidates.")
        return result
