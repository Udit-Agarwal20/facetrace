"""
FaceTrace — Step 3 Live Base Sepolia Smoke Test
Executes real on-chain transaction anchoring and contract verification against Base Sepolia.

GATE RULE:
This test is explicitly separated and only executes when RUN_LIVE_BLOCKCHAIN_TESTS=1.
It does NOT run during offline CI or regular unit test discovery.
"""

import json
import os
import unittest
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")

from src.blockchain.canonicalizer import EvidenceCanonicalizer
from src.blockchain.client import BlockchainClient
from src.blockchain.models import BlockchainMode, BlockchainReleaseStatus, BlockchainState


@unittest.skipUnless(
    os.getenv("RUN_LIVE_BLOCKCHAIN_TESTS") == "1",
    "Live Base Sepolia smoke tests disabled. Set RUN_LIVE_BLOCKCHAIN_TESTS=1 to run."
)
class TestLiveBaseSepoliaSmoke(unittest.TestCase):

    def setUp(self):
        self.evidence_path = project_root / "data" / "discovered_post.json"
        self.rpc_url = os.getenv("BASE_SEPOLIA_RPC_URL", "https://sepolia.base.org")
        self.private_key = os.getenv("BLOCKCHAIN_PRIVATE_KEY") or os.getenv("PRIVATE_KEY")
        self.contract_address = os.getenv("BLOCKCHAIN_CONTRACT_ADDRESS") or os.getenv("EVIDENCE_REGISTRY_ADDRESS")

    def test_live_base_sepolia_anchoring_and_readback(self):
        # 1. Check RPC connection and Chain ID
        client = BlockchainClient(
            rpc_url=self.rpc_url,
            contract_address=self.contract_address,
            private_key=self.private_key,
            chain_id=84532,
            mode=BlockchainMode.LIVE_BLOCKCHAIN
        )

        if not client.is_connected():
            self.fail(f"STEP3_LIVE_BLOCKCHAIN_BLOCKED: Cannot connect to Base Sepolia RPC at {self.rpc_url}")

        actual_chain_id = client.w3.eth.chain_id
        self.assertEqual(
            actual_chain_id, 84532,
            f"STEP3_LIVE_BLOCKCHAIN_BLOCKED: Chain ID mismatch. Expected 84532, got {actual_chain_id}"
        )

        # 2. Check Wallet
        if not self.private_key or not client.account:
            self.fail("STEP3_LIVE_BLOCKCHAIN_BLOCKED: BLOCKCHAIN_PRIVATE_KEY missing in .env")

        balance_wei = client.w3.eth.get_balance(client.address)
        if balance_wei == 0:
            self.fail(
                f"STEP3_LIVE_BLOCKCHAIN_BLOCKED: Wallet {client.address} has 0 ETH on Base Sepolia. "
                f"Fund via https://base.org/faucets"
            )

        # 3. Check Contract Bytecode
        if not self.contract_address:
            self.fail("STEP3_LIVE_BLOCKCHAIN_BLOCKED: BLOCKCHAIN_CONTRACT_ADDRESS missing in .env")

        code = client.w3.eth.get_code(client.contract_address)
        if not code or code in [b"", b"\x00"] or code.hex() in ["0x", "", "0x00"]:
            self.fail(
                f"STEP3_LIVE_BLOCKCHAIN_BLOCKED: Contract {client.contract_address} has no deployed bytecode on Base Sepolia"
            )

        # 4. Load Step 2 Evidence
        self.assertTrue(self.evidence_path.exists(), "Step 2 evidence file data/discovered_post.json not found")
        with open(self.evidence_path, "r", encoding="utf-8") as f:
            evidence_data = json.load(f)

        # 5. Canonicalize and Hash
        canonical_str = EvidenceCanonicalizer.canonicalize(evidence_data)
        evidence_hash = EvidenceCanonicalizer.compute_evidence_hash(canonical_str)
        self.assertTrue(evidence_hash.startswith("0x") and len(evidence_hash) == 66)

        # 6. Anchor to Base Sepolia
        record = client.anchor_evidence(evidence_hash, raise_on_error=True)
        self.assertIn(record.anchor_status, ("CONFIRMED", "ALREADY_ANCHORED"))
        self.assertEqual(record.blockchain_status, BlockchainReleaseStatus.LIVE_CONFIRMED)
        self.assertEqual(record.network, "base_sepolia")
        self.assertEqual(record.chain_id, 84532)

        # 7. Read-back from Contract
        exists, timestamp, submitter = client.verify_evidence(evidence_hash)
        self.assertTrue(exists, "Evidence commitment not found on-chain during read-back")
        self.assertGreater(timestamp, 0)
        self.assertTrue(client.w3.is_address(submitter))

        # 8. Compare Local Hash vs On-Chain
        comparison = client.verify_local_against_chain(evidence_hash)
        self.assertTrue(comparison.is_verified)
        self.assertEqual(comparison.state, BlockchainState.VERIFICATION_PASS)
        self.assertEqual(comparison.local_hash, evidence_hash)
        self.assertEqual(comparison.on_chain_hash, evidence_hash)

        # 9. Tamper Simulation
        tampered_data = json.loads(json.dumps(evidence_data))
        tampered_data["selected_candidate"]["page_url"] += "_tampered"
        tampered_canonical = EvidenceCanonicalizer.canonicalize(tampered_data)
        tampered_hash = EvidenceCanonicalizer.compute_evidence_hash(tampered_canonical)

        self.assertNotEqual(evidence_hash, tampered_hash)
        tampered_comparison = client.verify_local_against_chain(tampered_hash)
        self.assertFalse(tampered_comparison.is_verified)
        self.assertEqual(tampered_comparison.state, BlockchainState.VERIFICATION_FAIL)


if __name__ == "__main__":
    unittest.main()
