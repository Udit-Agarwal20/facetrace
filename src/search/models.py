"""
Data contracts and domain models for Step 2 Reverse Image Search Architecture.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, Union
import numpy as np


class MatchClassification(str, Enum):
    EXACT = "EXACT"
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    SIMILAR = "SIMILAR"
    UNKNOWN = "UNKNOWN"


class VerificationClassification(str, Enum):
    VERIFIED_EXACT = "VERIFIED_EXACT"
    VERIFIED_DERIVATIVE = "VERIFIED_DERIVATIVE"
    PROBABLE_MATCH = "PROBABLE_MATCH"
    UNVERIFIED = "UNVERIFIED"
    REJECTED = "REJECTED"


class ExecutionMode(str, Enum):
    LIVE_EXTERNAL_SEARCH = "LIVE_EXTERNAL_SEARCH"
    CACHE_REPLAY = "CACHE_REPLAY"
    MOCK_PROVIDER = "MOCK_PROVIDER"


class DiscoveryType(str, Enum):
    IMAGE_PROVENANCE = "image_provenance"
    FACE_SEARCH = "face_search"


class Task3ComplianceState(str, Enum):
    TASK3_SOCIAL_MATCH = "TASK3_SOCIAL_MATCH"
    WEB_MATCH_ONLY = "WEB_MATCH_ONLY"
    NO_SOCIAL_MATCH = "NO_SOCIAL_MATCH"
    INCONCLUSIVE = "INCONCLUSIVE"
    SEARCH_UNAVAILABLE = "SEARCH_UNAVAILABLE"
    REJECTED = "REJECTED"
    NOT_FINAL_TASK3_PASS = "NOT_FINAL_TASK3_PASS"
    TEST_ONLY = "TEST_ONLY"


class CandidateOutcome(str, Enum):
    VERIFIED_MATCH = "VERIFIED_MATCH"
    VERIFIED_WEB_MATCH = "VERIFIED_WEB_MATCH"
    UNREACHABLE = "UNREACHABLE"
    REJECTED = "REJECTED"
    VERIFICATION_ERROR = "VERIFICATION_ERROR"
    NOT_SOCIAL = "NOT_SOCIAL"
    TASK3_DISQUALIFIED = "TASK3_DISQUALIFIED"
    NOT_ATTEMPTED_DUE_TO_BUDGET = "NOT_ATTEMPTED_DUE_TO_BUDGET"


@dataclass
class RetrievalDetails:
    source_reachable: bool = False
    evidence_retrieved: bool = False
    image_valid: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_reachable": self.source_reachable,
            "evidence_retrieved": self.evidence_retrieved,
            "image_valid": self.image_valid,
            "error": self.error
        }


@dataclass
class Task3ComplianceDetails:
    state: Task3ComplianceState
    passed: bool
    failed_gates: List[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "passed": self.passed,
            "failed_gates": self.failed_gates,
            "reason": self.reason
        }


@dataclass
class FaceBoundingBox:
    x: float
    y: float
    width: float
    height: float

    @classmethod
    def from_list(cls, bbox: List[float]) -> "FaceBoundingBox":
        """Accepts [x1, y1, x2, y2] from InsightFace and converts to x, y, width, height."""
        if len(bbox) == 4:
            x1, y1, x2, y2 = bbox
            return cls(x=x1, y=y1, width=x2 - x1, height=y2 - y1)
        raise ValueError(f"Invalid bbox list: {bbox}")

    def to_xyxy(self) -> List[float]:
        return [self.x, self.y, self.x + self.width, self.y + self.height]


@dataclass
class FaceInfo:
    bbox: FaceBoundingBox
    aligned_face: Optional[str] = None
    embedding: Optional[Union[List[float], np.ndarray]] = None
    detection_score: float = 0.0


@dataclass
class SearchRequest:
    job_id: str
    original_image: str  # Path to query image
    face: FaceInfo
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VerificationDetails:
    classification: VerificationClassification
    sha256_exact: bool = False
    sha256_candidate: Optional[str] = None
    phash_distance: Optional[int] = None
    face_verified: bool = False
    face_similarity: Optional[float] = None
    faces_detected: int = 0
    best_face_index: Optional[int] = None
    retrieval: Optional[RetrievalDetails] = None
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "classification": self.classification.value,
            "verification_state": self.classification.value,
            "sha256_exact": self.sha256_exact,
            "sha256_candidate": self.sha256_candidate,
            "phash_distance": self.phash_distance,
            "phash": {
                "available": self.phash_distance is not None,
                "distance": self.phash_distance
            },
            "face_verified": self.face_verified,
            "face_similarity": round(self.face_similarity, 4) if self.face_similarity is not None else None,
            "faces_detected": self.faces_detected,
            "best_face_index": self.best_face_index,
            "face": {
                "detected": self.faces_detected > 0,
                "verified": self.face_verified,
                "model": "ArcFace",
                "similarity": round(self.face_similarity, 4) if self.face_similarity is not None else None,
                "faces_detected": self.faces_detected,
                "selected_face_index": self.best_face_index
            },
            "retrieval": self.retrieval.to_dict() if self.retrieval else None,
            "explanation": self.explanation
        }


@dataclass
class DiscoveredCandidate:
    candidate_id: str
    provider: str
    query_variants: List[str] = field(default_factory=list)  # ["original", "face_crop"]
    provider_match_type: MatchClassification = MatchClassification.UNKNOWN
    page_url: str = ""
    image_url: Optional[str] = None
    page_title: Optional[str] = None
    provider_score: float = 0.0
    platform: Optional[str] = None
    is_external_source: bool = True
    is_social_domain: bool = False
    is_post_url: bool = False
    retrieval_score: float = 0.0
    verification: Optional[VerificationDetails] = None
    retrieval: Optional[RetrievalDetails] = None
    task3_compliance: Optional[Task3ComplianceDetails] = None
    candidate_outcome: Optional[str] = None
    outcome_reason: Optional[str] = None
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "provider": self.provider,
            "query_variants": self.query_variants,
            "provider_match_type": self.provider_match_type.value,
            "page_url": self.page_url,
            "image_url": self.image_url,
            "page_title": self.page_title,
            "provider_score": round(self.provider_score, 4),
            "platform": self.platform,
            "is_external_source": self.is_external_source,
            "is_social_domain": self.is_social_domain,
            "is_post_url": self.is_post_url,
            "retrieval_score": round(self.retrieval_score, 4),
            "candidate_outcome": self.candidate_outcome,
            "outcome_reason": self.outcome_reason,
            "retrieval": self.retrieval.to_dict() if self.retrieval else (self.verification.retrieval.to_dict() if self.verification and self.verification.retrieval else None),
            "verification": self.verification.to_dict() if self.verification else None,
            "task3_compliance": self.task3_compliance.to_dict() if self.task3_compliance else None
        }


@dataclass
class Step2Output:
    job_id: str
    status: str  # SOCIAL_POST_MATCH_FOUND | WEB_MATCH_FOUND | NO_SOCIAL_MATCH_FOUND | SEARCH_UNAVAILABLE
    search: Dict[str, Any]
    selected_candidate: Optional[Dict[str, Any]]
    provenance: Dict[str, Any]
    task3_compliance: Optional[Dict[str, Any]] = None
    retrieval: Optional[Dict[str, Any]] = None
    schema_version: str = "1.0"
    all_candidates: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    investigation_summary: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "status": self.status,
            "task3_compliance": self.task3_compliance,
            "search": self.search,
            "selected_candidate": self.selected_candidate,
            "retrieval": self.retrieval or (self.selected_candidate.get("retrieval") if self.selected_candidate else None),
            "verification": (self.selected_candidate.get("verification") if self.selected_candidate else None),
            "provenance": self.provenance,
            "all_candidates": self.all_candidates,
            "metrics": self.metrics,
            "investigation_summary": self.investigation_summary
        }
