"""
FaceTrace Blockchain Package
Provides evidence canonicalization, commitment generation, and Base Sepolia contract integration.
"""

from src.blockchain.models import (
    BlockchainState,
    BlockchainMode,
    BlockchainRecord,
    VerificationComparisonResult
)
from src.blockchain.canonicalizer import (
    EvidenceCanonicalizer,
    NonCompliantEvidenceError
)
from src.blockchain.client import (
    BlockchainClient,
    MockBlockchainClient
)

__all__ = [
    "BlockchainState",
    "BlockchainMode",
    "BlockchainRecord",
    "VerificationComparisonResult",
    "EvidenceCanonicalizer",
    "NonCompliantEvidenceError",
    "BlockchainClient",
    "MockBlockchainClient"
]
