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
    Task3ComplianceState,
    CandidateOutcome
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
        max_verification_candidates: int = 25,
        max_social_candidates: int = 15,
        max_web_candidates: int = 10
    ):
        self.provider = provider or GoogleVisionProvider()
        self.query_generator = query_generator or QueryVariantGenerator()
        self.normalizer = normalizer or ResponseNormalizer()
        self.deduplicator = deduplicator or CandidateDeduplicator()
        self.ranker = ranker or CandidateRanker()
        self.verifier = verifier or MultiLevelVerifier()
        self.cache = cache or SearchCache()
        self.max_verification_candidates = max_verification_candidates
        self.max_social_candidates = max_social_candidates
        self.max_web_candidates = max_web_candidates

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
                reason_msg = "The reverse-image provider returned no indexed matches for this image."

            empty_summary = {
                "total_discovered": 0,
                "unique_candidates": 0,
                "social_candidates": 0,
                "candidates_analyzed": 0,
                "verified_web_matches": 0,
                "qualifying_social_matches": 0,
                "unreachable_candidates": 0,
                "rejected_candidates": 0,
                "disqualified_candidates": 0,
                "budget_skipped": 0,
                "budget_skipped_candidates": 0,
                "strongest_match": "None",
                "strongest_web_match": None,
                "strongest_social_match": None,
                "social_evidence": "Search provider error encountered." if provider_errors else "No indexed matches returned by provider.",
                "social_evidence_note": (
                    "Search provider error encountered." if provider_errors else "No indexed matches returned by provider."
                ),
                "task3_evidence": "NOT ESTABLISHED",
                "task3_status": "NOT ESTABLISHED",
                "blockchain_status": "NOT ANCHORED (No qualifying evidence available)"
            }

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
                metrics={"raw_candidate_count": 0, "deduplicated_count": 0},
                investigation_summary=empty_summary
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
        # Partition candidates into social pool and general-web pool
        social_pool = [c for c in ranked if c.is_social_domain]
        web_pool = [c for c in ranked if not c.is_social_domain]

        # Prioritize social candidates up to max_social_candidates and total cap
        social_budget = min(len(social_pool), self.max_social_candidates, self.max_verification_candidates)
        social_to_verify = social_pool[:social_budget]

        remaining_budget = max(0, self.max_verification_candidates - len(social_to_verify))
        web_budget = min(len(web_pool), self.max_web_candidates, remaining_budget)
        web_to_verify = web_pool[:web_budget]

        candidates_to_verify = social_to_verify + web_to_verify
        verified_candidate_ids = {c.candidate_id for c in candidates_to_verify}

        # Mark all candidates not selected for analysis due to budget
        for c in ranked:
            if c.candidate_id not in verified_candidate_ids:
                c.candidate_outcome = CandidateOutcome.NOT_ATTEMPTED_DUE_TO_BUDGET.value
                c.outcome_reason = "Candidate was not analyzed because verification budget was reached."

        qualifying_social_posts: List[DiscoveredCandidate] = []
        web_matches_only: List[DiscoveredCandidate] = []
        failed_candidates: List[DiscoveredCandidate] = []

        logger.info(
            f"[{job_id}] Running best-effort verification on {len(candidates_to_verify)} candidates "
            f"(budget: {len(social_to_verify)} social, {len(web_to_verify)} web)..."
        )
        for cand in candidates_to_verify:
            try:
                # Run image/face verification
                details = self.verifier.verify(
                    candidate=cand,
                    original_image_path=original_img_path,
                    query_face=request.face
                )
            except Exception as e:
                logger.warning(f"[{job_id}] Verification error on candidate {cand.candidate_id}: {e}")
                err_str = str(e).lower()
                if any(x in err_str for x in ["400", "403", "404", "timeout", "unreachable", "inaccessible", "connection", "bad request"]):
                    cand.candidate_outcome = CandidateOutcome.UNREACHABLE.value
                    cand.outcome_reason = f"Candidate asset unreachable: {e}"
                else:
                    cand.candidate_outcome = CandidateOutcome.VERIFICATION_ERROR.value
                    cand.outcome_reason = f"Verification exception: {e}"
                failed_candidates.append(cand)
                continue

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

            # Classify candidate outcome
            retrieval = cand.retrieval or details.retrieval
            is_unreachable = (
                not retrieval
                or not retrieval.source_reachable
                or not retrieval.evidence_retrieved
                or not retrieval.image_valid
            )

            if is_unreachable:
                cand.candidate_outcome = CandidateOutcome.UNREACHABLE.value
                cand.outcome_reason = (retrieval.error if retrieval else None) or details.explanation or "Candidate image unreachable or invalid"
                failed_candidates.append(cand)
                logger.info(f"[{job_id}] Candidate {cand.candidate_id} unreachable: {cand.outcome_reason}")
            elif comp_details.state == Task3ComplianceState.TASK3_SOCIAL_MATCH:
                cand.candidate_outcome = CandidateOutcome.VERIFIED_MATCH.value
                cand.outcome_reason = comp_details.reason
                qualifying_social_posts.append(cand)
                logger.info(f"[{job_id}] Candidate {cand.candidate_id} passed TASK 3 COMPLIANCE GATE: {cand.platform} post (similarity: {details.face_similarity})")
            elif comp_details.state in (Task3ComplianceState.TEST_ONLY, Task3ComplianceState.NOT_FINAL_TASK3_PASS):
                cand.candidate_outcome = CandidateOutcome.VERIFIED_MATCH.value
                cand.outcome_reason = comp_details.reason
                qualifying_social_posts.append(cand)
                logger.info(f"[{job_id}] Candidate {cand.candidate_id} passed test criteria in mode {comp_details.state.value}")
            elif comp_details.state == Task3ComplianceState.WEB_MATCH_ONLY:
                cand.candidate_outcome = CandidateOutcome.VERIFIED_WEB_MATCH.value
                cand.outcome_reason = comp_details.reason
                web_matches_only.append(cand)
                logger.info(f"[{job_id}] Candidate {cand.candidate_id} verified as WEB_MATCH_ONLY (similarity: {details.face_similarity})")
            elif cand.is_social_domain and not cand.is_post_url:
                cand.candidate_outcome = CandidateOutcome.TASK3_DISQUALIFIED.value
                cand.outcome_reason = comp_details.reason
                failed_candidates.append(cand)
                logger.info(f"[{job_id}] Candidate {cand.candidate_id} disqualified: social domain but not a post URL")
            elif not cand.is_social_domain and not details.face_verified:
                cand.candidate_outcome = CandidateOutcome.REJECTED.value
                cand.outcome_reason = details.explanation or "Face similarity below threshold on web match"
                failed_candidates.append(cand)
                logger.info(f"[{job_id}] Candidate {cand.candidate_id} rejected: {cand.outcome_reason}")
            else:
                cand.candidate_outcome = CandidateOutcome.REJECTED.value
                cand.outcome_reason = comp_details.reason or details.explanation or "Candidate failed verification"
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
                "failed_gates": ["NO_MATCH (The search returned visually related web images, but no candidate matched the submitted face or satisfied the required social-post provenance)"],
                "reason": "The search returned visually related web images, but no candidate matched the submitted face or satisfied the required social-post provenance."
            }

        # Compute forensic investigation summary
        unreachable_count = sum(1 for c in ranked if c.candidate_outcome == CandidateOutcome.UNREACHABLE.value)
        rejected_count = sum(1 for c in ranked if c.candidate_outcome == CandidateOutcome.REJECTED.value)
        disqualified_count = sum(1 for c in ranked if c.candidate_outcome == CandidateOutcome.TASK3_DISQUALIFIED.value)
        verified_social_count = len(qualifying_social_posts)
        verified_web_count = len(web_matches_only)
        budget_skipped_count = sum(1 for c in ranked if c.candidate_outcome == CandidateOutcome.NOT_ATTEMPTED_DUE_TO_BUDGET.value)
        analyzed_count = len(candidates_to_verify)

        strongest_web = None
        if web_matches_only:
            best_web = sorted(web_matches_only, key=lambda c: (c.verification.face_similarity or 0.0), reverse=True)[0]
            strongest_web = {
                "platform": best_web.platform or best_web.page_url,
                "page_url": best_web.page_url,
                "face_similarity": best_web.verification.face_similarity if best_web.verification else None,
                "classification": best_web.verification.classification.value if best_web.verification else None
            }

        strongest_social = None
        if qualifying_social_posts:
            best_social = sorted(qualifying_social_posts, key=lambda c: (c.verification.face_similarity or 0.0), reverse=True)[0]
            strongest_social = {
                "platform": best_social.platform,
                "page_url": best_social.page_url,
                "face_similarity": best_social.verification.face_similarity if best_social.verification else None,
                "classification": best_social.verification.classification.value if best_social.verification else None
            }

        if verified_social_count > 0:
            social_evidence_note = f"Verified qualifying social post discovered on {strongest_social['platform'].capitalize()}."
        elif social_count > 0 and unreachable_count > 0:
            social_evidence_note = f"Discovered {social_count} social candidates, but media assets could not be independently retrieved (platform anti-crawler restrictions)."
        elif social_count > 0:
            social_evidence_note = f"Discovered {social_count} social candidates, but none met content post criteria or matched face."
        else:
            social_evidence_note = "No social candidates indexed by provider."

        strongest_label = "None"
        if strongest_social and strongest_social.get("face_similarity") is not None:
            strongest_label = f"{strongest_social['platform']} — ArcFace {strongest_social['face_similarity']:.4f}"
        elif strongest_web and strongest_web.get("face_similarity") is not None:
            strongest_label = f"{strongest_web['platform']} — ArcFace {strongest_web['face_similarity']:.4f}"

        investigation_summary = {
            "total_discovered": raw_count,
            "unique_candidates": dedup_count,
            "social_candidates": social_count,
            "candidates_analyzed": analyzed_count,
            "verified_web_matches": verified_web_count,
            "qualifying_social_matches": verified_social_count,
            "unreachable_candidates": unreachable_count,
            "rejected_candidates": rejected_count,
            "disqualified_candidates": disqualified_count,
            "budget_skipped": budget_skipped_count,
            "budget_skipped_candidates": budget_skipped_count,
            "strongest_match": strongest_label,
            "strongest_web_match": strongest_web,
            "strongest_social_match": strongest_social,
            "social_evidence": social_evidence_note,
            "social_evidence_note": social_evidence_note,
            "task3_evidence": "QUALIFYING EVIDENCE ESTABLISHED" if verified_social_count > 0 else "NOT ESTABLISHED",
            "task3_status": "ESTABLISHED" if verified_social_count > 0 else "NOT ESTABLISHED",
            "blockchain_status": "ANCHORED ON BASE SEPOLIA" if verified_social_count > 0 else "NOT ANCHORED (No qualifying social evidence available)"
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
                "unreachable_count": unreachable_count,
                "budget_skipped_count": budget_skipped_count,
                "total_latency_ms": round(total_latency_ms, 1)
            },
            investigation_summary=investigation_summary
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
