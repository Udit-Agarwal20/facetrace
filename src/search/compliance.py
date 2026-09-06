"""
FaceTrace Task 3 Compliance Engine.
Evaluates candidate discovery and verification against the mandatory Hackathon Task 3 requirements:
- LIVE_EXTERNAL_SEARCH
- EXTERNAL_SOURCE
- SOCIAL_DOMAIN
- POST_LIKE_URL
- SOURCE_REACHABLE
- EVIDENCE_RETRIEVABLE
- VALID_CANDIDATE_IMAGE
- FACE_DETECTED
- ARCFACE_VERIFIED
"""

from typing import Dict, Any, List, Optional
import logging

from .models import (
    DiscoveredCandidate,
    VerificationDetails,
    Task3ComplianceDetails,
    Task3ComplianceState,
    ExecutionMode,
    VerificationClassification
)

logger = logging.getLogger(__name__)

# Search engines / internal URLs explicitly disallowed as external evidence sources
DISALLOWED_DOMAINS = {
    "facecheck.id",
    "www.facecheck.id",
    "google.com",
    "www.google.com",
    "lens.google.com",
    "tineye.com",
    "www.tineye.com",
    "bing.com",
    "www.bing.com",
    "yandex.com",
    "localhost",
    "127.0.0.1"
}


def evaluate_task3_candidate(
    candidate: DiscoveredCandidate,
    verification: Optional[VerificationDetails],
    execution_context: Dict[str, Any]
) -> Task3ComplianceDetails:
    """
    Evaluates a candidate against the mandatory Task 3 compliance gates.
    Only candidates satisfying ALL mandatory conditions receive TASK3_SOCIAL_MATCH.
    """
    failed_gates: List[str] = []
    mode: ExecutionMode = execution_context.get("execution_mode", ExecutionMode.LIVE_EXTERNAL_SEARCH)
    if isinstance(mode, str):
        try:
            mode = ExecutionMode(mode)
        except ValueError:
            mode = ExecutionMode.LIVE_EXTERNAL_SEARCH

    # 1. LIVE_EXTERNAL_SEARCH Gate
    if mode == ExecutionMode.MOCK_PROVIDER:
        failed_gates.append("LIVE_EXTERNAL_SEARCH (Executed via Mock Provider for testing)")
    elif mode == ExecutionMode.CACHE_REPLAY:
        failed_gates.append("LIVE_EXTERNAL_SEARCH (Replayed from local SHA-256 development cache)")

    # 2. EXTERNAL_SOURCE Gate
    from urllib.parse import urlparse
    parsed = urlparse(candidate.page_url)
    netloc = (parsed.netloc.lower().split(":")[0]) if parsed.netloc else ""
    if not netloc or netloc in DISALLOWED_DOMAINS or any(netloc.endswith("." + d) for d in DISALLOWED_DOMAINS):
        failed_gates.append(f"EXTERNAL_SOURCE (Disallowed or internal domain: {netloc or 'none'})")

    # 3. SOCIAL_DOMAIN Gate
    if not candidate.is_social_domain or not candidate.platform:
        failed_gates.append(f"SOCIAL_DOMAIN (Domain {netloc} is not a supported social-media platform)")

    # 4. POST_LIKE_URL Gate
    if not candidate.is_post_url:
        failed_gates.append(f"POST_LIKE_URL (URL path '{parsed.path}' is not a post/content URL)")

    # 5. RETRIEVABILITY & IMAGE VALIDITY GATES
    retrieval = candidate.retrieval or (verification.retrieval if verification else None)
    if retrieval:
        if not retrieval.source_reachable:
            failed_gates.append(f"SOURCE_REACHABLE ({retrieval.error or 'Candidate source page could not be reached'})")
        if not retrieval.evidence_retrieved:
            failed_gates.append(f"EVIDENCE_RETRIEVABLE ({retrieval.error or 'Candidate image could not be retrieved'})")
        if not retrieval.image_valid:
            failed_gates.append(f"VALID_CANDIDATE_IMAGE ({retrieval.error or 'Candidate image is not valid or decodable'})")
    else:
        # Fallback inspection if retrieval object is absent
        if not verification or verification.classification == VerificationClassification.UNVERIFIED:
            failed_gates.append("EVIDENCE_RETRIEVABLE (Candidate image could not be obtained for verification)")

    # 6. FACE DETECTION & ARCFACE VERIFICATION GATES
    if not verification:
        failed_gates.append("FACE_DETECTED (Candidate has not undergone verification)")
        failed_gates.append("ARCFACE_VERIFIED (Candidate has not undergone verification)")
    else:
        if verification.faces_detected == 0:
            failed_gates.append("FACE_DETECTED (No face detected in candidate image)")
        if not verification.face_verified:
            sim_str = f"{verification.face_similarity:.4f}" if verification.face_similarity is not None else "None"
            failed_gates.append(f"ARCFACE_VERIFIED (Face similarity {sim_str} does not meet verification threshold)")

    # --------------------------------------------------------------------------
    # DETERMINE COMPLIANCE STATE
    # --------------------------------------------------------------------------
    has_external_fail = any("EXTERNAL_SOURCE" in g for g in failed_gates)
    is_social_post = candidate.is_social_domain and candidate.is_post_url
    is_verified = verification and verification.classification in (
        VerificationClassification.VERIFIED_EXACT,
        VerificationClassification.VERIFIED_DERIVATIVE
    )

    if not failed_gates:
        state = Task3ComplianceState.TASK3_SOCIAL_MATCH
        passed = True
        reason = (
            f"Candidate was genuinely discovered during live external search, is a verified social post on {candidate.platform.capitalize()}, "
            f"evidence was retrieved, and candidate face independently passed ArcFace verification (similarity: {verification.face_similarity:.4f})."
        )
    elif mode == ExecutionMode.MOCK_PROVIDER and is_social_post and is_verified:
        state = Task3ComplianceState.TEST_ONLY
        passed = False
        reason = "Candidate matches test criteria but execution used offline MockProvider; not qualifying for Task 3 final acceptance."
    elif mode == ExecutionMode.CACHE_REPLAY and is_social_post and is_verified:
        state = Task3ComplianceState.NOT_FINAL_TASK3_PASS
        passed = False
        reason = "Candidate verified from cached results; Task 3 compliance requires fresh live search execution."
    elif has_external_fail:
        state = Task3ComplianceState.REJECTED
        passed = False
        reason = "Candidate is from an internal placeholder or search-provider domain and was rejected as a valid external evidence source."
    elif candidate.is_social_domain and not candidate.is_post_url:
        state = Task3ComplianceState.REJECTED
        passed = False
        reason = "Candidate is on a social-media domain but is a homepage, profile, login, or search URL rather than a content/post URL."
    elif not candidate.is_social_domain and is_verified and not has_external_fail:
        state = Task3ComplianceState.WEB_MATCH_ONLY
        passed = False
        reason = "Candidate passed image and face verification but is a generic web article/page and therefore does not satisfy the Task 3 social-media-post requirement."
    elif verification and verification.classification == VerificationClassification.UNVERIFIED:
        state = Task3ComplianceState.INCONCLUSIVE
        passed = False
        reason = f"Candidate evidence verification unavailable: {verification.explanation}"
    elif verification and verification.classification == VerificationClassification.REJECTED:
        state = Task3ComplianceState.REJECTED
        passed = False
        reason = f"Candidate failed verification: {verification.explanation}"
    else:
        state = Task3ComplianceState.REJECTED
        passed = False
        reason = f"Candidate failed Task 3 mandatory compliance gates: {', '.join(failed_gates)}"

    return Task3ComplianceDetails(
        state=state,
        passed=passed,
        failed_gates=failed_gates,
        reason=reason
    )
