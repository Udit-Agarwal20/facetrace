"""
Search Orchestrator for Step 2 Reverse Image Search and Verification Subsystem.
Master coordinator managing query variant generation, provider execution, normalization,
deduplication, ranking, multi-level verification, and Step 3 evidence package generation.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
import json
import logging
import time

from .models import (
    SearchRequest,
    DiscoveredCandidate,
    Step2Output,
    VerificationClassification,
    ExecutionMode,
    DiscoveryType,
    Task3ComplianceState
)
from .compliance import evaluate_task3_candidate
from .query_variants import QueryVariantGenerator
from .providers.base import SearchProvider
from .providers.google_vision import GoogleVisionProvider
from .providers.mock_provider import MockSearchProvider
from .normalizer import ResponseNormalizer
from .deduplicator import CandidateDeduplicator
from .platform_classifier import PlatformClassifier
from .ranker import CandidateRanker
from .verifier import MultiLevelVerifier
from .cache import SearchCache

logger = logging.getLogger("FaceTrace.SearchOrchestrator")


class SearchOrchestrator:
    """Controls the entire Step 2 reverse-image retrieval and verification workflow."""

    def __init__(
        self,
        provider: Optional[SearchProvider] = None,
        query_generator: Optional[QueryVariantGenerator] = None,
        normalizer: Optional[ResponseNormalizer] = None,
        deduplicator: Optional[CandidateDeduplicator] = None,
        ranker: Optional[CandidateRanker] = None,
        verifier: Optional[MultiLevelVerifier] = None,
        cache: Optional[SearchCache] = None,
        max_verification_candidates: int = 10
    ):
        self.provider = provider or GoogleVisionProvider()
        self.query_generator = query_generator or QueryVariantGenerator()
        self.normalizer = normalizer or ResponseNormalizer()
        self.deduplicator = deduplicator or CandidateDeduplicator()
        self.ranker = ranker or CandidateRanker()
        self.verifier = verifier or MultiLevelVerifier()
        self.cache = cache or SearchCache()
        self.max_verification_candidates = max_verification_candidates

    def search(
        self,
        request: SearchRequest,
        output_path: Optional[Path] = None,
        require_live: bool = False
    ) -> Step2Output:
        """
        Executes Step 2 pipeline:
        SearchRequest -> Dual Queries -> Provider -> Normalize -> Deduplicate ->
        Two-Layer Rank -> Multi-level Verify -> Task 3 Compliance Gate -> Step2Output
        """
        total_start = time.time()
        job_id = request.job_id
        original_img_path = Path(request.original_image).resolve()

        logger.info(f"[{job_id}] Starting Step 2 Reverse Image Search for {original_img_path.name} (require_live={require_live})...")

        now_iso = datetime.now(timezone.utc).isoformat()
        if not original_img_path.exists():
            return Step2Output(
                schema_version="1.0",
                job_id=job_id,
                status="SEARCH_UNAVAILABLE",
                task3_compliance={
                    "state": Task3ComplianceState.SEARCH_UNAVAILABLE.value,
                    "passed": False,
                    "failed_gates": ["Original image not found"],
                    "reason": f"Input image does not exist: {original_img_path}"
                },
                search={"provider": self.provider.name, "error": "Original image not found"},
                selected_candidate=None,
                provenance={"retrieved_at": now_iso, "provider": self.provider.name}
            )

        # ----------------------------------------------------------------------
        # 1. Generate Query Variants (Query A = Original, Query B = Padded Face Crop)
        # ----------------------------------------------------------------------
        variants = self.query_generator.generate(
            original_image_path=original_img_path,
            bbox=request.face.bbox,
            job_id=job_id
        )

        all_raw_candidates: List[DiscoveredCandidate] = []
        queries_executed = 0
        total_provider_latency_ms = 0.0
        provider_errors: List[str] = []

        try:
            # ------------------------------------------------------------------
            # 2. Execute Query A (Original Image)
            # ------------------------------------------------------------------
            logger.info(f"[{job_id}] Executing Query A (Original image)...")
            cached_a = None if require_live else self.cache.get(variants.original_path, self.provider.name)
            if cached_a is not None:
                resp_a_candidates = cached_a
                lat_a = 0.0
            else:
                resp_a = self.provider.search(variants.original_path)
                queries_executed += 1
                lat_a = resp_a.latency_ms
                total_provider_latency_ms += lat_a
                if resp_a.success:
                    self.cache.set(variants.original_path, self.provider.name, resp_a.candidates)
                    resp_a_candidates = resp_a.candidates
                else:
                    logger.warning(f"[{job_id}] Query A failed: {resp_a.error}")
                    provider_errors.append(f"Query A: {resp_a.error}")
                    resp_a_candidates = []

            norm_a = self.normalizer.normalize(resp_a_candidates, self.provider.name, query_variant="original")
            all_raw_candidates.extend(norm_a)
            logger.info(f"[{job_id}] Query A discovered {len(norm_a)} candidates ({lat_a:.0f}ms).")

            # ------------------------------------------------------------------
            # 3. Execute Query B (Padded Face Crop)
            # ------------------------------------------------------------------
            logger.info(f"[{job_id}] Executing Query B (Padded face crop)...")
            cached_b = None if require_live else self.cache.get(variants.face_crop_path, self.provider.name)
            if cached_b is not None:
                resp_b_candidates = cached_b
                lat_b = 0.0
            else:
                resp_b = self.provider.search(variants.face_crop_path)
                queries_executed += 1
                lat_b = resp_b.latency_ms
                total_provider_latency_ms += lat_b
                if resp_b.success:
                    self.cache.set(variants.face_crop_path, self.provider.name, resp_b.candidates)
                    resp_b_candidates = resp_b.candidates
                else:
                    logger.warning(f"[{job_id}] Query B failed: {resp_b.error}")
                    provider_errors.append(f"Query B: {resp_b.error}")
                    resp_b_candidates = []

            norm_b = self.normalizer.normalize(resp_b_candidates, self.provider.name, query_variant="face_crop")
            all_raw_candidates.extend(norm_b)
            logger.info(f"[{job_id}] Query B discovered {len(norm_b)} candidates ({lat_b:.0f}ms).")

        finally:
            # Clean up temporary face crop file
            variants.cleanup()

        # Determine ExecutionMode
        if self.provider.name == "mock_provider" or isinstance(self.provider, MockSearchProvider):
            execution_mode = ExecutionMode.MOCK_PROVIDER
        elif queries_executed == 0:
            execution_mode = ExecutionMode.CACHE_REPLAY
        else:
            execution_mode = ExecutionMode.LIVE_EXTERNAL_SEARCH

        raw_count = len(all_raw_candidates)
        if raw_count == 0:
            if provider_errors:
                status = "SEARCH_UNAVAILABLE"
                comp_state = Task3ComplianceState.SEARCH_UNAVAILABLE
                reason_msg = f"Search provider failure: {'; '.join(provider_errors)}"
            else:
                status = "NO_SOCIAL_MATCH_FOUND"
                comp_state = Task3ComplianceState.NO_SOCIAL_MATCH
                reason_msg = "Google Vision returned 0 search candidates."

            logger.info(f"[{job_id}] Search finished with 0 candidates returned ({status}).")
            return Step2Output(
                schema_version="1.0",
                job_id=job_id,
                status=status,
                task3_compliance={
                    "state": comp_state.value,
                    "passed": False,
                    "failed_gates": provider_errors or ["NO_MATCH"],
                    "reason": reason_msg
                },
                search={
                    "provider": self.provider.name,
                    "discovery_type": DiscoveryType.IMAGE_PROVENANCE.value,
                    "execution_mode": execution_mode.value,
                    "queries_executed": queries_executed,
                    "provider_latency_ms": round(total_provider_latency_ms, 1)
                },
                selected_candidate=None,
                provenance={
                    "discovered_at": now_iso,
                    "retrieved_at": now_iso,
                    "verified_at": now_iso,
                    "provider": f"{self.provider.name}_web_detection",
                    "discovery_type": DiscoveryType.IMAGE_PROVENANCE.value,
                    "execution_mode": execution_mode.value
                },
                all_candidates=[],
                metrics={"raw_candidate_count": 0, "deduplicated_count": 0}
            )

        # ----------------------------------------------------------------------
        # 4. Deduplicate Candidates & Merge Multi-Query Appearances
        # ----------------------------------------------------------------------
        deduped = self.deduplicator.deduplicate(all_raw_candidates)
        dedup_count = len(deduped)

        # ----------------------------------------------------------------------
        # 5. Rank Candidates by Retrieval Signals (Two-Layer Model: Social Posts First)
        # ----------------------------------------------------------------------
        ranked = self.ranker.rank(deduped)
        social_count = sum(1 for c in ranked if c.is_social_domain)
        post_count = sum(1 for c in ranked if c.is_post_url)
        logger.info(f"[{job_id}] Pool metrics: {dedup_count} unique, {social_count} social domains, {post_count} post-like URLs.")

        # ----------------------------------------------------------------------
        # 6. Multi-Level Verification Ladder & Task 3 Hard Compliance Gating
        # ----------------------------------------------------------------------
        candidates_to_verify = ranked[:self.max_verification_candidates]
        qualifying_social_posts: List[DiscoveredCandidate] = []
        web_matches_only: List[DiscoveredCandidate] = []
        failed_candidates: List[DiscoveredCandidate] = []

        logger.info(f"[{job_id}] Running verification ladder & compliance gate on top {len(candidates_to_verify)} ranked candidates...")
        for cand in candidates_to_verify:
            # Run image/face verification
            details = self.verifier.verify(
                candidate=cand,
                original_image_path=original_img_path,
                query_face=request.face
            )
            cand.verification = details

            # Evaluate against mandatory Task 3 Compliance Gates
            comp_details = evaluate_task3_candidate(
                candidate=cand,
                verification=details,
                execution_context={
                    "execution_mode": execution_mode,
                    "provider_name": self.provider.name
                }
            )
            cand.task3_compliance = comp_details

            # Categorize candidates
            if comp_details.state == Task3ComplianceState.TASK3_SOCIAL_MATCH:
                qualifying_social_posts.append(cand)
                logger.info(f"[{job_id}] Candidate {cand.candidate_id} passed TASK 3 COMPLIANCE GATE: {cand.platform} post (similarity: {details.face_similarity})")
            elif comp_details.state in (Task3ComplianceState.TEST_ONLY, Task3ComplianceState.NOT_FINAL_TASK3_PASS):
                qualifying_social_posts.append(cand)
                logger.info(f"[{job_id}] Candidate {cand.candidate_id} passed test criteria in mode {comp_details.state.value}")
            elif comp_details.state == Task3ComplianceState.WEB_MATCH_ONLY:
                web_matches_only.append(cand)
                logger.info(f"[{job_id}] Candidate {cand.candidate_id} verified as WEB_MATCH_ONLY (non-social domain)")
            else:
                failed_candidates.append(cand)
                logger.info(f"[{job_id}] Candidate {cand.candidate_id} rejected: {comp_details.reason}")

        # ----------------------------------------------------------------------
        # 7. Select Best Qualifying Candidate (Enforcing Hard Social Post Preference)
        # ----------------------------------------------------------------------
        selected_candidate: Optional[DiscoveredCandidate] = None
        task3_compliance_output: Dict[str, Any]

        if qualifying_social_posts:
            # Rank qualifying social posts by face similarity, then exact match, then retrieval score
            def social_sort_key(c: DiscoveredCandidate):
                sim = c.verification.face_similarity if (c.verification and c.verification.face_similarity is not None) else 0.0
                exact = 1 if (c.verification and c.verification.classification == VerificationClassification.VERIFIED_EXACT) else 0
                return (exact, sim, c.retrieval_score)

            sorted_social = sorted(qualifying_social_posts, key=social_sort_key, reverse=True)
            selected_candidate = sorted_social[0]
            status = "SOCIAL_POST_MATCH_FOUND"
            task3_compliance_output = selected_candidate.task3_compliance.to_dict()
        elif web_matches_only:
            # Verified web articles preserved as supporting evidence, but NOT satisfying Task 3 social post
            def web_sort_key(c: DiscoveredCandidate):
                sim = c.verification.face_similarity if (c.verification and c.verification.face_similarity is not None) else 0.0
                exact = 1 if (c.verification and c.verification.classification == VerificationClassification.VERIFIED_EXACT) else 0
                return (exact, sim, c.retrieval_score)

            sorted_web = sorted(web_matches_only, key=web_sort_key, reverse=True)
            selected_candidate = sorted_web[0]
            status = "WEB_MATCH_FOUND"
            task3_compliance_output = {
                "state": Task3ComplianceState.WEB_MATCH_ONLY.value,
                "passed": False,
                "failed_gates": ["SOCIAL_DOMAIN (Selected match is a generic web article/page, not a qualifying social-media post)"],
                "reason": "Candidate passed image and face verification but is a generic web article/page and therefore does not satisfy the Task 3 social-media-post requirement."
            }
        else:
            status = "NO_SOCIAL_MATCH_FOUND"
            task3_compliance_output = {
                "state": Task3ComplianceState.NO_SOCIAL_MATCH.value,
                "passed": False,
                "failed_gates": ["NO_MATCH (Zero candidates satisfied image verification and Task 3 compliance requirements)"],
                "reason": "Zero candidates satisfied image verification and Task 3 compliance requirements."
            }

        total_latency_ms = (time.time() - total_start) * 1000
        discovered_ts = now_iso
        retrieved_ts = datetime.now(timezone.utc).isoformat()
        verified_ts = datetime.now(timezone.utc).isoformat()

        output = Step2Output(
            schema_version="1.0",
            job_id=job_id,
            status=status,
            task3_compliance=task3_compliance_output,
            search={
                "provider": self.provider.name,
                "discovery_type": DiscoveryType.IMAGE_PROVENANCE.value,
                "execution_mode": execution_mode.value,
                "queries_executed": queries_executed,
                "provider_latency_ms": round(total_provider_latency_ms, 1)
            },
            selected_candidate=selected_candidate.to_dict() if selected_candidate else None,
            retrieval=selected_candidate.retrieval.to_dict() if (selected_candidate and selected_candidate.retrieval) else None,
            provenance={
                "discovered_at": discovered_ts,
                "retrieved_at": retrieved_ts,
                "verified_at": verified_ts,
                "provider": f"{self.provider.name}_web_detection",
                "discovery_type": DiscoveryType.IMAGE_PROVENANCE.value,
                "execution_mode": execution_mode.value
            },
            all_candidates=[c.to_dict() for c in ranked],
            metrics={
                "raw_candidate_count": raw_count,
                "deduplicated_count": dedup_count,
                "social_candidate_count": social_count,
                "post_url_count": post_count,
                "verified_candidate_count": len(qualifying_social_posts) + len(web_matches_only),
                "qualifying_social_post_count": len(qualifying_social_posts),
                "web_matches_only_count": len(web_matches_only),
                "total_latency_ms": round(total_latency_ms, 1)
            }
        )

        logger.info(
            f"[{job_id}] Step 2 Completed: status={status}, compliance={task3_compliance_output.get('state')}, "
            f"selected={selected_candidate.page_url if selected_candidate else 'None'} (Total latency: {total_latency_ms:.0f}ms)"
        )

        # Write to output file if requested
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(output.to_dict(), f, indent=2)
            logger.info(f"[{job_id}] Saved validated evidence package ready for cryptographic commitment to {output_path}")

        return output
