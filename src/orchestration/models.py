"""
FaceTrace — Step 4 Orchestration Models & State Machine
Defines explicit pipeline stages, execution modes, failure states,
and the final unified result model.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List


class PipelineStage(str, Enum):
    INIT = "INIT"
    INPUT_VALIDATED = "INPUT_VALIDATED"
    CONSENT_CONFIRMED = "CONSENT_CONFIRMED"
    FACE_DETECTED = "FACE_DETECTED"
    FACE_EMBEDDED = "FACE_EMBEDDED"
    SEARCH_RUNNING = "SEARCH_RUNNING"
    SEARCH_COMPLETE = "SEARCH_COMPLETE"
    CANDIDATE_SELECTED = "CANDIDATE_SELECTED"
    SOCIAL_COMPLIANCE_PASSED = "SOCIAL_COMPLIANCE_PASSED"
    FACE_VERIFICATION_PASSED = "FACE_VERIFICATION_PASSED"
    EVIDENCE_VALIDATED = "EVIDENCE_VALIDATED"
    EVIDENCE_HASHED = "EVIDENCE_HASHED"
    BLOCKCHAIN_ANCHORING = "BLOCKCHAIN_ANCHORING"
    BLOCKCHAIN_CONFIRMED = "BLOCKCHAIN_CONFIRMED"
    ONCHAIN_VERIFIED = "ONCHAIN_VERIFIED"
    TAMPER_TEST_COMPLETE = "TAMPER_TEST_COMPLETE"
    COMPLETE = "COMPLETE"

    # Explicit Failure States
    INPUT_ERROR = "INPUT_ERROR"
    NO_FACE = "NO_FACE"
    SEARCH_ERROR = "SEARCH_ERROR"
    NO_MATCH = "NO_MATCH"
    SOCIAL_REQUIREMENT_FAILED = "SOCIAL_REQUIREMENT_FAILED"
    FACE_VERIFICATION_FAILED = "FACE_VERIFICATION_FAILED"
    EVIDENCE_INVALID = "EVIDENCE_INVALID"
    BLOCKCHAIN_ERROR = "BLOCKCHAIN_ERROR"
    BLOCKCHAIN_VERIFICATION_FAILED = "BLOCKCHAIN_VERIFICATION_FAILED"
    TAMPER_DETECTED = "TAMPER_DETECTED"


class ExecutionMode(str, Enum):
    LIVE = "LIVE"
    MOCK = "MOCK"
    DRY_RUN = "DRY_RUN"


class PipelineStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    DEMO_NOT_FINAL = "DEMO_NOT_FINAL"


@dataclass
class CandidateSummary:
    platform: str = ""
    post_url: str = ""
    image_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform": self.platform,
            "post_url": self.post_url,
            "image_url": self.image_url
        }


@dataclass
class VerificationSummary:
    face_similarity: Optional[float] = None
    sha256_exact: bool = False
    phash_distance: Optional[int] = None
    state: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "face_similarity": self.face_similarity,
            "sha256_exact": self.sha256_exact,
            "phash_distance": self.phash_distance,
            "state": self.state
        }


@dataclass
class BlockchainSummary:
    network: str = "base_sepolia"
    chain_id: int = 84532
    contract_address: str = ""
    evidence_hash: str = ""
    transaction_hash: Optional[str] = None
    block_number: Optional[int] = None
    anchor_status: str = "PENDING"
    anchor_mode: str = "NEW"  # NEW | EXISTING_RECOVERY | LOCAL_TEST | MOCK
    blockchain_status: str = "LIVE_CONFIRMED"
    verification_status: str = "PENDING"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "network": self.network,
            "chain_id": self.chain_id,
            "contract_address": self.contract_address,
            "evidence_hash": self.evidence_hash,
            "transaction_hash": self.transaction_hash,
            "block_number": self.block_number,
            "anchor_status": self.anchor_status,
            "anchor_mode": self.anchor_mode,
            "blockchain_status": self.blockchain_status,
            "verification_status": self.verification_status
        }


@dataclass
class TamperTestSummary:
    status: str = "TAMPER_DETECTED"
    original_hash: str = ""
    tampered_hash: str = ""
    onchain_hash: str = ""
    is_tamper_detected: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "original_hash": self.original_hash,
            "tampered_hash": self.tampered_hash,
            "onchain_hash": self.onchain_hash,
            "is_tamper_detected": self.is_tamper_detected
        }


@dataclass
class TimingsSummary:
    face_processing_ms: float = 0.0
    search_ms: float = 0.0
    retrieval_ms: float = 0.0
    verification_ms: float = 0.0
    blockchain_ms: float = 0.0
    total_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "face_processing_ms": round(self.face_processing_ms, 1),
            "search_ms": round(self.search_ms, 1),
            "retrieval_ms": round(self.retrieval_ms, 1),
            "verification_ms": round(self.verification_ms, 1),
            "blockchain_ms": round(self.blockchain_ms, 1),
            "total_ms": round(self.total_ms, 1)
        }


@dataclass
class FaceTraceRunResult:
    run_id: str
    status: PipelineStatus
    stage: PipelineStage
    execution_mode: ExecutionMode
    discovery_type: str = "image_provenance"
    verification_type: str = ""
    task3_compliance: str = ""
    candidate: Optional[CandidateSummary] = None
    verification: Optional[VerificationSummary] = None
    blockchain: Optional[BlockchainSummary] = None
    tamper_test: Optional[TamperTestSummary] = None
    timings_ms: TimingsSummary = field(default_factory=TimingsSummary)
    evidence: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    error_action: Optional[str] = None
    history: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Returns the final structured result model complying with Step 4 specifications."""
        res: Dict[str, Any] = {
            "run_id": self.run_id,
            "status": self.status.value,
            "stage": self.stage.value,
            "execution_mode": self.execution_mode.value,
            "discovery_type": self.discovery_type,
            "verification_type": self.verification_type,
            "task3_compliance": self.task3_compliance,
            "candidate": self.candidate.to_dict() if self.candidate else None,
            "verification": self.verification.to_dict() if self.verification else None,
            "blockchain": self.blockchain.to_dict() if self.blockchain else None,
            "tamper_test": self.tamper_test.to_dict() if self.tamper_test else None,
            "timings_ms": self.timings_ms.to_dict(),
            "error": self.error,
            "history": self.history
        }
        if self.evidence:
            res["evidence"] = self.evidence
        return res
