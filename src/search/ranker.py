"""
Candidate Ranker for Search Subsystem.
Calculates multi-signal retrieval scores to prioritize candidates for verification.
"""

from typing import List
import logging

from .models import DiscoveredCandidate, MatchClassification

logger = logging.getLogger(__name__)

MATCH_TYPE_BASE_SCORES = {
    MatchClassification.EXACT: 1.00,
    MatchClassification.FULL: 0.85,
    MatchClassification.PARTIAL: 0.65,
    MatchClassification.SIMILAR: 0.35,
    MatchClassification.UNKNOWN: 0.20
}


class CandidateRanker:
    """
    Ranks candidates based on multiple retrieval signals:
    - Match type (FULL > PARTIAL > SIMILAR)
    - Dual query variant presence (found by both original & face crop)
    - Direct page -> image association
    - Social platform domain
    - Post-like URL structure
    """

    def rank(self, candidates: List[DiscoveredCandidate]) -> List[DiscoveredCandidate]:
        """
        Calculates retrieval_score for each candidate and returns candidates sorted descending.
        """
        for cand in candidates:
            base_score = MATCH_TYPE_BASE_SCORES.get(cand.provider_match_type, 0.20)
            score = base_score

            # Dual query bonus: found in both original and face crop
            if len(cand.query_variants) > 1:
                score += 0.25

            # Direct image URL available on page
            if cand.image_url and cand.page_url:
                score += 0.15

            # Social domain bonus
            if cand.is_social_domain:
                score += 0.20

            # Post-like URL structure bonus
            if cand.is_post_url:
                score += 0.25

            # Provider confidence score weighting (scale 0-1)
            score += (cand.provider_score * 0.10)

            cand.retrieval_score = round(score, 4)

        # Two-Layer Hierarchy:
        # Layer 1: Compliance Pre-filter / Categorization (Social Post > Social Domain > Generic Web)
        # Layer 2: Retrieval score ranking within each tier
        def rank_key(c: DiscoveredCandidate):
            is_social_post = 1 if (c.is_social_domain and c.is_post_url) else 0
            is_social = 1 if c.is_social_domain else 0
            return (is_social_post, is_social, c.retrieval_score)

        ranked = sorted(candidates, key=rank_key, reverse=True)
        top_str = f"score={ranked[0].retrieval_score}, platform={ranked[0].platform}, post={ranked[0].is_post_url}" if ranked else "none"
        logger.info(f"[Candidate Ranker] Ranked {len(ranked)} candidates (Two-Layer Model: Social Posts first). Top: {top_str}")
        return ranked
