"""
FaceTrace — Blockchain Data Models & State Machine
Defines states, execution modes, and record structures for Step 3.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any


class BlockchainState(str, Enum):
    NOT_READY = "NOT_READY"
    VALIDATED = "VALIDATED"
    HASHED = "HASHED"
    ANCHOR_PENDING = "ANCHOR_PENDING"
    ANCHORED = "ANCHORED"
    VERIFICATION_PASS = "VERIFICATION_PASS"
    VERIFICATION_FAIL = "VERIFICATION_FAIL"
    TAMPER_DETECTED = "TAMPER_DETECTED"
    BLOCKCHAIN_ERROR = "BLOCKCHAIN_ERROR"


class BlockchainMode(str, Enum):
    LIVE_BLOCKCHAIN = "LIVE_BLOCKCHAIN"
    LOCAL_TEST = "LOCAL_TEST"
    MOCK_BLOCKCHAIN = "MOCK_BLOCKCHAIN"


class BlockchainReleaseStatus(str, Enum):
    LIVE_CONFIRMED = "LIVE_CONFIRMED"
    LOCAL_TEST = "LOCAL_TEST"
    TEST_ONLY = "TEST_ONLY"
    STEP3_LIVE_BLOCKCHAIN_BLOCKED = "STEP3_LIVE_BLOCKCHAIN_BLOCKED"


@dataclass
class BlockchainRecord:
    network: str = "base_sepolia"
    chain_id: int = 84532
    contract_address: str = ""
    evidence_hash: str = ""
    transaction_hash: Optional[str] = None
    block_number: Optional[int] = None
    timestamp: Optional[int] = None
    submitter: Optional[str] = None
    anchor_status: str = "PENDING"
    verification_status: str = "PENDING"
    blockchain_status: BlockchainReleaseStatus = BlockchainReleaseStatus.TEST_ONLY
    execution_mode: BlockchainMode = BlockchainMode.LIVE_BLOCKCHAIN
    error: Optional[str] = None

    def __post_init__(self):
        # Strict anti-false-pass rules
        if self.blockchain_status == BlockchainReleaseStatus.LIVE_CONFIRMED:
            if self.execution_mode != BlockchainMode.LIVE_BLOCKCHAIN:
                raise ValueError("Anti-false-pass violation: Non-live execution mode cannot be classified as LIVE_CONFIRMED.")
            if self.network != "base_sepolia":
                raise ValueError("Anti-false-pass violation: Non-Base-Sepolia network cannot be classified as LIVE_CONFIRMED.")
            if self.chain_id != 84532:
                raise ValueError("Anti-false-pass violation: Chain ID must be 84532 for LIVE_CONFIRMED.")
            if self.transaction_hash:
                tx_lower = self.transaction_hash.lower()
                if "mock" in tx_lower or tx_lower == "0x" + "0" * 64:
                    raise ValueError("Anti-false-pass violation: Mock or fake transaction hash cannot be classified as LIVE_CONFIRMED.")
        elif self.execution_mode == BlockchainMode.MOCK_BLOCKCHAIN:
            if self.blockchain_status not in (BlockchainReleaseStatus.TEST_ONLY, BlockchainReleaseStatus.STEP3_LIVE_BLOCKCHAIN_BLOCKED):
                raise ValueError("Anti-false-pass violation: Mock blockchain mode must have blockchain_status == TEST_ONLY.")
        elif self.execution_mode == BlockchainMode.LOCAL_TEST:
            if self.blockchain_status not in (BlockchainReleaseStatus.LOCAL_TEST, BlockchainReleaseStatus.STEP3_LIVE_BLOCKCHAIN_BLOCKED):
                raise ValueError("Anti-false-pass violation: Local EVM test mode cannot have blockchain_status == LIVE_CONFIRMED.")
            if self.network == "base_sepolia":
                raise ValueError("Anti-false-pass violation: Local EVM test cannot be classified as Base Sepolia network.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "network": self.network,
            "chain_id": self.chain_id,
            "contract_address": self.contract_address,
            "evidence_hash": self.evidence_hash,
            "transaction_hash": self.transaction_hash,
            "block_number": self.block_number,
            "timestamp": self.timestamp,
            "submitter": self.submitter,
            "anchor_status": self.anchor_status,
            "verification_status": self.verification_status,
            "blockchain_status": self.blockchain_status.value,
            "execution_mode": self.execution_mode.value,
            "error": self.error
        }


@dataclass
class VerificationComparisonResult:
    state: BlockchainState
    is_verified: bool
    local_hash: str
    on_chain_hash: Optional[str]
    timestamp: Optional[int] = None
    submitter: Optional[str] = None
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "is_verified": self.is_verified,
            "local_hash": self.local_hash,
            "on_chain_hash": self.on_chain_hash,
            "timestamp": self.timestamp,
            "submitter": self.submitter,
            "reason": self.reason
        }
