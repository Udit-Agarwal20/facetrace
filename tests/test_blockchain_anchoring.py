"""
FaceTrace — Step 3 Blockchain Anchoring & Verification Test Suite
Tests deterministic canonicalization, commitments, contract execution,
tamper detection, secrets masking, and failure recovery.
"""

import copy
import io
import json
import logging
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from web3 import Web3
from web3.providers.eth_tester import EthereumTesterProvider

from src.blockchain.canonicalizer import (
    EvidenceCanonicalizer,
    NonCompliantEvidenceError
)
from src.blockchain.client import (
    BlockchainClient,
    MockBlockchainClient
)
from src.blockchain.models import (
    BlockchainState,
    BlockchainMode,
    BlockchainRecord,
    BlockchainReleaseStatus
)


class TestBlockchainAnchoringSuite(unittest.TestCase):

    def setUp(self):
        # Sample validated Step 2 evidence package
        self.sample_evidence = {
            "schema_version": "1.0",
            "job_id": "scan_test_12345",
            "status": "SOCIAL_POST_MATCH_FOUND",
            "task3_compliance": {
                "state": "TASK3_SOCIAL_MATCH",
                "passed": True,
                "failed_gates": []
            },
            "search": {
                "provider": "google_vision",
                "discovery_type": "image_provenance",
                "execution_mode": "LIVE_EXTERNAL_SEARCH",
                "queries_executed": 2
            },
            "selected_candidate": {
                "candidate_id": "cand_test_001",
                "page_url": "https://www.reddit.com/r/southpaws/comments/z1yuo/i_knew_obama_was_a_lefty_but_im_surprised_he",
                "image_url": "http://allthingsd.com/files/2012/08/Barack-Obama-Reddit.jpeg",
                "platform": "reddit",
                "is_social_domain": True,
                "is_post_url": True,
                "verification": {
                    "classification": "VERIFIED_EXACT",
                    "verification_state": "VERIFIED_EXACT",
                    "sha256_exact": True,
                    "sha256_candidate": "f8f141c421f4e52cc7255bc3741572659478a60b59ffe1fc888802661efc8e5e",
                    "phash_distance": 0,
                    "face_verified": True,
                    "face_similarity": 1.0,
                    "faces_detected": 1,
                    "best_face_index": 0
                }
            }
        }

    # 1. Deterministic Canonicalization
    def test_deterministic_canonicalization(self):
        canonical1 = EvidenceCanonicalizer.canonicalize(self.sample_evidence)
        # Permute dictionary keys in a shallow copy
        reordered = {k: self.sample_evidence[k] for k in reversed(list(self.sample_evidence.keys()))}
        canonical2 = EvidenceCanonicalizer.canonicalize(reordered)
        self.assertEqual(canonical1, canonical2)
        self.assertTrue(canonical1.startswith('{"candidate_image_phash":0'))

    # 2. Same Evidence -> Same Hash
    def test_same_evidence_same_hash(self):
        hash1 = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)
        hash2 = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)
        self.assertEqual(hash1, hash2)
        self.assertTrue(hash1.startswith("0x"))
        self.assertEqual(len(hash1), 66)

    # 3. Different Evidence -> Different Hash
    def test_different_evidence_different_hash(self):
        hash1 = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)

        # Mutate URL
        mutated = copy.deepcopy(self.sample_evidence)
        mutated["selected_candidate"]["page_url"] = "https://www.reddit.com/r/other/comments/different"
        hash2 = EvidenceCanonicalizer.compute_evidence_hash(mutated)
        self.assertNotEqual(hash1, hash2)

        # Mutate similarity
        mutated2 = copy.deepcopy(self.sample_evidence)
        mutated2["selected_candidate"]["verification"]["face_similarity"] = 0.9999
        hash3 = EvidenceCanonicalizer.compute_evidence_hash(mutated2)
        self.assertNotEqual(hash1, hash3)

    # 4. Successful Contract Anchoring (Real Local EVM Provider)
    def test_successful_contract_anchoring_evm(self):
        w3 = Web3(EthereumTesterProvider())
        deployer = w3.eth.accounts[0]

        artifact_path = Path(__file__).parent.parent / "contracts" / "EvidenceRegistry.json"
        with open(artifact_path, "r", encoding="utf-8") as f:
            artifact = json.load(f)

        Registry = w3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
        tx = Registry.constructor().transact({"from": deployer})
        receipt = w3.eth.wait_for_transaction_receipt(tx)
        contract_addr = receipt.contractAddress

        client = BlockchainClient(
            contract_address=contract_addr,
            w3=w3,
            mode=BlockchainMode.LOCAL_TEST
        )

        evidence_hash = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)
        record = client.anchor_evidence(evidence_hash)

        self.assertEqual(record.anchor_status, "CONFIRMED")
        self.assertIsNotNone(record.transaction_hash)
        self.assertIsNotNone(record.block_number)
        self.assertIsNotNone(record.timestamp)

    # 5. Transaction Receipt Handling
    def test_transaction_receipt_handling(self):
        client = MockBlockchainClient()
        evidence_hash = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)
        record = client.anchor_evidence(evidence_hash)
        self.assertEqual(record.anchor_status, "CONFIRMED")
        self.assertTrue(record.transaction_hash.startswith("0xmocktx"))
        self.assertGreater(record.block_number, 0)

    # 6. On-Chain Lookup
    def test_on_chain_lookup(self):
        client = MockBlockchainClient()
        evidence_hash = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)
        client.anchor_evidence(evidence_hash)

        exists, timestamp, submitter = client.verify_evidence(evidence_hash)
        self.assertTrue(exists)
        self.assertGreater(timestamp, 0)
        self.assertEqual(submitter, client.mock_submitter)

    # 7. Local Hash == On-Chain Hash (Match)
    def test_local_hash_matches_on_chain_commitment(self):
        client = MockBlockchainClient()
        evidence_hash = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)
        client.anchor_evidence(evidence_hash)

        recomputed_hash = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)
        comparison = client.verify_local_against_chain(recomputed_hash)

        self.assertTrue(comparison.is_verified)
        self.assertEqual(comparison.state, BlockchainState.VERIFICATION_PASS)
        self.assertEqual(comparison.local_hash, recomputed_hash)
        self.assertEqual(comparison.on_chain_hash, recomputed_hash)

    # 8. Tampered Evidence Detected
    def test_tampered_evidence_detected(self):
        client = MockBlockchainClient()
        original_hash = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)
        client.anchor_evidence(original_hash)

        # Tamper with evidence
        tampered_evidence = copy.deepcopy(self.sample_evidence)
        tampered_evidence["selected_candidate"]["page_url"] += "_tampered"
        tampered_hash = EvidenceCanonicalizer.compute_evidence_hash(tampered_evidence)

        comparison = client.verify_local_against_chain(tampered_hash)
        self.assertFalse(comparison.is_verified)
        self.assertEqual(comparison.state, BlockchainState.VERIFICATION_FAIL)
        self.assertNotEqual(original_hash, tampered_hash)

    # 9. Invalid Task-3 Evidence Cannot Be Anchored
    def test_non_compliant_evidence_rejected(self):
        # Case A: WEB_MATCH_ONLY
        web_evidence = copy.deepcopy(self.sample_evidence)
        web_evidence["task3_compliance"]["state"] = "WEB_MATCH_ONLY"
        with self.assertRaises(NonCompliantEvidenceError):
            EvidenceCanonicalizer.extract_canonical_fields(web_evidence)

        # Case B: NO_SOCIAL_MATCH
        no_match = copy.deepcopy(self.sample_evidence)
        no_match["task3_compliance"]["state"] = "NO_SOCIAL_MATCH"
        with self.assertRaises(NonCompliantEvidenceError):
            EvidenceCanonicalizer.extract_canonical_fields(no_match)

        # Case C: REJECTED
        rejected_ev = copy.deepcopy(self.sample_evidence)
        rejected_ev["task3_compliance"]["state"] = "REJECTED"
        with self.assertRaises(NonCompliantEvidenceError):
            EvidenceCanonicalizer.extract_canonical_fields(rejected_ev)

        # Case D: Unverified classification
        unverif_ev = copy.deepcopy(self.sample_evidence)
        unverif_ev["selected_candidate"]["verification"]["verification_state"] = "REJECTED"
        with self.assertRaises(NonCompliantEvidenceError):
            EvidenceCanonicalizer.extract_canonical_fields(unverif_ev)

    # 10. Secrets Are Never Printed or Leaked
    def test_secrets_never_printed_or_leaked(self):
        dummy_secret = "0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d"
        client = BlockchainClient(
            contract_address="0x1111111111111111111111111111111111111111",
            private_key=dummy_secret
        )

        # Check client string representation or record representation
        record = BlockchainRecord(
            contract_address=client.contract_address,
            evidence_hash="0x" + "0" * 64,
            transaction_hash="0x" + "1" * 64
        )
        record_dict = record.to_dict()
        record_json = json.dumps(record_dict)

        self.assertNotIn(dummy_secret, record_json)
        self.assertNotIn(dummy_secret[2:], record_json)

    # 11. Duplicate Evidence Handled Gracefully
    def test_duplicate_evidence_handling(self):
        client = MockBlockchainClient()
        evidence_hash = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)

        rec1 = client.anchor_evidence(evidence_hash)
        self.assertEqual(rec1.anchor_status, "CONFIRMED")

        # Second anchor attempt
        rec2 = client.anchor_evidence(evidence_hash)
        self.assertEqual(rec2.anchor_status, "ALREADY_ANCHORED")
        self.assertEqual(rec2.verification_status, "MATCH")

    # 12. Invalid Evidence Hash Handled
    def test_invalid_evidence_hash_handled(self):
        client = MockBlockchainClient()
        with self.assertRaises(ValueError):
            client.anchor_evidence("short_hash")
        with self.assertRaises(ValueError):
            client.anchor_evidence("not_0x_prefixed_64_characters_hash_here_1234567890123456789012345678901")

    # 13. Missing Contract Address Handled
    def test_missing_contract_address_handled(self):
        client = BlockchainClient(contract_address=None, private_key="0x" + "a" * 64)
        with self.assertRaises(ValueError):
            client.anchor_evidence("0x" + "0" * 64)

    # 14. Missing Private Key Handled
    def test_missing_private_key_handled(self):
        client = BlockchainClient(
            contract_address="0x1111111111111111111111111111111111111111",
            private_key=None
        )
        # When w3 has no accounts
        client.w3 = MagicMock()
        client.w3.eth.accounts = []
        with self.assertRaises(ValueError):
            client.anchor_evidence("0x" + "0" * 64)

    # 15. RPC Connection Failure Handled
    def test_rpc_failure_handled(self):
        client = BlockchainClient(
            rpc_url="http://127.0.0.1:59999",  # Non-existent RPC
            contract_address="0x1111111111111111111111111111111111111111",
            timeout=1
        )
        self.assertFalse(client.is_connected())

    # 16. Anti-False-Pass: Mock transaction cannot be classified as LIVE_CONFIRMED
    def test_mock_transaction_cannot_be_classified_as_live_confirmed(self):
        client = MockBlockchainClient()
        evidence_hash = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)
        rec = client.anchor_evidence(evidence_hash)
        self.assertEqual(rec.blockchain_status, BlockchainReleaseStatus.TEST_ONLY)
        self.assertNotEqual(rec.blockchain_status, BlockchainReleaseStatus.LIVE_CONFIRMED)

        # Attempting to forge a LIVE_CONFIRMED record with MOCK_BLOCKCHAIN must raise ValueError
        with self.assertRaises(ValueError) as ctx:
            BlockchainRecord(
                network="base_sepolia",
                chain_id=84532,
                contract_address="0x1111111111111111111111111111111111111111",
                evidence_hash=evidence_hash,
                transaction_hash="0xmocktx000123456789012345678901234567890123456789012345678901234567",
                blockchain_status=BlockchainReleaseStatus.LIVE_CONFIRMED,
                execution_mode=BlockchainMode.MOCK_BLOCKCHAIN
            )
        self.assertIn("Anti-false-pass violation", str(ctx.exception))

        # Attempting to use a mock transaction hash with LIVE_CONFIRMED must raise ValueError
        with self.assertRaises(ValueError) as ctx2:
            BlockchainRecord(
                network="base_sepolia",
                chain_id=84532,
                contract_address="0x1111111111111111111111111111111111111111",
                evidence_hash=evidence_hash,
                transaction_hash="0xmocktx000123456789012345678901234567890123456789012345678901234567",
                blockchain_status=BlockchainReleaseStatus.LIVE_CONFIRMED,
                execution_mode=BlockchainMode.LIVE_BLOCKCHAIN
            )
        self.assertIn("Anti-false-pass violation", str(ctx2.exception))

    # 17. Anti-False-Pass: Local EVM cannot be classified as Base Sepolia
    def test_local_evm_cannot_be_classified_as_base_sepolia(self):
        evidence_hash = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)

        # Attempting to assign network="base_sepolia" with LOCAL_TEST execution mode must raise ValueError
        with self.assertRaises(ValueError) as ctx:
            BlockchainRecord(
                network="base_sepolia",
                chain_id=1337,
                contract_address="0x1111111111111111111111111111111111111111",
                evidence_hash=evidence_hash,
                blockchain_status=BlockchainReleaseStatus.LOCAL_TEST,
                execution_mode=BlockchainMode.LOCAL_TEST
            )
        self.assertIn("Local EVM test cannot be classified as Base Sepolia", str(ctx.exception))

        # Attempting to assign LIVE_CONFIRMED to LOCAL_TEST must raise ValueError
        with self.assertRaises(ValueError) as ctx2:
            BlockchainRecord(
                network="local_evm",
                chain_id=1337,
                contract_address="0x1111111111111111111111111111111111111111",
                evidence_hash=evidence_hash,
                blockchain_status=BlockchainReleaseStatus.LIVE_CONFIRMED,
                execution_mode=BlockchainMode.LOCAL_TEST
            )
        self.assertIn("Anti-false-pass violation", str(ctx2.exception))

    # 18. Anti-False-Pass: Missing RPC causes explicit failure in live mode
    def test_missing_rpc_causes_explicit_failure(self):
        with self.assertRaises(ValueError) as ctx:
            BlockchainClient(
                rpc_url="",
                contract_address="0x1111111111111111111111111111111111111111",
                private_key="0x" + "a" * 64,
                mode=BlockchainMode.LIVE_BLOCKCHAIN
            )
        self.assertIn("Missing RPC URL for Base Sepolia", str(ctx.exception))

    # 19. Anti-False-Pass: Missing private key causes explicit failure in live mode
    def test_missing_private_key_causes_explicit_failure_in_live_mode(self):
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.chain_id = 84532
        mock_w3.eth.accounts = []

        client = BlockchainClient(
            contract_address="0x1111111111111111111111111111111111111111",
            private_key=None,
            w3=mock_w3,
            mode=BlockchainMode.LIVE_BLOCKCHAIN
        )
        evidence_hash = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)
        with self.assertRaises(ValueError) as ctx:
            client.anchor_evidence(evidence_hash)
        self.assertIn("No private key configured", str(ctx.exception))

    # 20. Anti-False-Pass: Wrong chain ID causes explicit failure in live mode
    def test_wrong_chain_id_causes_explicit_failure(self):
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.chain_id = 1  # Mainnet instead of Base Sepolia 84532
        mock_w3.eth.account.from_key.return_value.address = "0x2222222222222222222222222222222222222222"

        client = BlockchainClient(
            contract_address="0x1111111111111111111111111111111111111111",
            private_key="0x" + "b" * 64,
            w3=mock_w3,
            chain_id=84532,
            mode=BlockchainMode.LIVE_BLOCKCHAIN
        )
        evidence_hash = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)
        with self.assertRaises(ValueError) as ctx:
            client.anchor_evidence(evidence_hash)
        self.assertIn("Chain ID mismatch", str(ctx.exception))

    # 21. Anti-False-Pass: Fake transaction hash cannot pass validation
    def test_fake_transaction_hash_cannot_pass_validation(self):
        mock_w3 = MagicMock()
        mock_w3.eth.get_transaction.return_value = None  # Not found on chain

        client = BlockchainClient(
            contract_address="0x1111111111111111111111111111111111111111",
            w3=mock_w3,
            mode=BlockchainMode.LIVE_BLOCKCHAIN
        )
        # Invalid format
        self.assertFalse(client.validate_transaction_hash("invalid_format"))
        self.assertFalse(client.validate_transaction_hash("0x1234"))
        # Mock prefix
        self.assertFalse(client.validate_transaction_hash("0xmocktx000123456789012345678901234567890123456789012345678901234567"))
        # All zeros
        self.assertFalse(client.validate_transaction_hash("0x" + "0" * 64))
        # Nonexistent on chain
        self.assertFalse(client.validate_transaction_hash("0x" + "f" * 64))

    # 22. Anti-False-Pass: Transaction receipt status 0 cannot pass
    def test_transaction_receipt_status_0_cannot_pass(self):
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.chain_id = 84532
        account_mock = MagicMock()
        account_mock.address = "0x2222222222222222222222222222222222222222"
        mock_w3.eth.account.from_key.return_value = account_mock
        mock_w3.eth.get_code.return_value = b"\x60\x80\x60\x40"
        mock_w3.eth.get_balance.return_value = 10**18
        mock_w3.eth.get_transaction_count.return_value = 0
        mock_w3.eth.gas_price = 1000000
        mock_w3.eth.estimate_gas.return_value = 50000
        account_mock.sign_transaction.return_value.raw_transaction = b"\x00"
        mock_w3.eth.send_raw_transaction.return_value = b"\x01" * 32
        mock_w3.to_hex.return_value = "0x" + "01" * 32

        # Simulate reverted transaction receipt (status = 0)
        mock_w3.eth.wait_for_transaction_receipt.return_value = {
            "status": 0,
            "blockNumber": 12345,
            "transactionHash": "0x" + "01" * 32
        }

        client = BlockchainClient(
            contract_address="0x1111111111111111111111111111111111111111",
            private_key="0x" + "c" * 64,
            w3=mock_w3,
            mode=BlockchainMode.LIVE_BLOCKCHAIN
        )
        # Mock verifyEvidence so pre-check says not anchored yet
        client.contract = MagicMock()
        client.contract.functions.verifyEvidence.return_value.call.return_value = (False, 0, "0x0000000000000000000000000000000000000000")

        evidence_hash = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)

        # Must raise when raise_on_error=True
        with self.assertRaises(RuntimeError) as ctx:
            client.anchor_evidence(evidence_hash, raise_on_error=True)
        self.assertIn("Transaction failed on-chain with status 0", str(ctx.exception))

        # Default mode returns failed record with status STEP3_LIVE_BLOCKCHAIN_BLOCKED
        rec = client.anchor_evidence(evidence_hash, raise_on_error=False)
        self.assertEqual(rec.anchor_status, "FAILED")
        self.assertEqual(rec.blockchain_status, BlockchainReleaseStatus.STEP3_LIVE_BLOCKCHAIN_BLOCKED)
        self.assertIn("status 0", rec.error)

    # 23. Anti-False-Pass: Missing contract bytecode cannot pass
    def test_missing_contract_bytecode_cannot_pass(self):
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.chain_id = 84532
        account_mock = MagicMock()
        account_mock.address = "0x2222222222222222222222222222222222222222"
        mock_w3.eth.account.from_key.return_value = account_mock
        # Address has no code deployed
        mock_w3.eth.get_code.return_value = b""

        client = BlockchainClient(
            contract_address="0x1111111111111111111111111111111111111111",
            private_key="0x" + "d" * 64,
            w3=mock_w3,
            mode=BlockchainMode.LIVE_BLOCKCHAIN
        )
        evidence_hash = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)
        with self.assertRaises(ValueError) as ctx:
            client.anchor_evidence(evidence_hash)
        self.assertIn("does not contain deployed contract bytecode", str(ctx.exception))

    # 24. Anti-False-Pass: On-chain hash mismatch cannot pass
    def test_on_chain_hash_mismatch_cannot_pass(self):
        client = MockBlockchainClient()
        evidence_hash = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)
        client.anchor_evidence(evidence_hash)

        # Query with different hash
        different_hash = "0x" + "9" * 64
        comparison = client.verify_local_against_chain(different_hash)
        self.assertFalse(comparison.is_verified)
        self.assertEqual(comparison.state, BlockchainState.VERIFICATION_FAIL)
        self.assertIn("not found in mock on-chain registry", comparison.reason)

    # 25. Regression: Malformed block identifier handled gracefully
    def test_regression_malformed_block_identifier(self):
        mock_w3 = MagicMock()
        mock_w3.eth.get_block.side_effect = ValueError("Invalid block identifier format")
        client = BlockchainClient(
            contract_address="0x1111111111111111111111111111111111111111",
            w3=mock_w3,
            mode=BlockchainMode.LOCAL_TEST
        )
        res = client._get_block_with_retry("malformed_0xZZZ", max_retries=2, initial_delay=0.01)
        self.assertIsNone(res)

    # 26. Regression: Missing block with BlockNotFound retried and fallback
    def test_regression_missing_block_retry_and_fallback(self):
        from web3.exceptions import BlockNotFound
        mock_w3 = MagicMock()
        mock_w3.eth.get_block.side_effect = BlockNotFound("Block with id: '0x2c4e95d' not found.")
        client = BlockchainClient(
            contract_address="0x1111111111111111111111111111111111111111",
            w3=mock_w3,
            mode=BlockchainMode.LOCAL_TEST
        )
        res = client._get_block_with_retry(0x2c4e95d, max_retries=3, initial_delay=0.01)
        self.assertIsNone(res)
        self.assertGreaterEqual(mock_w3.eth.get_block.call_count, 3)

    # 27. Regression: Delayed receipt polling with backoff
    def test_regression_delayed_receipt_polling(self):
        from web3.exceptions import TransactionNotFound
        mock_w3 = MagicMock()
        receipt_obj = {"status": 1, "blockNumber": 100, "transactionHash": "0x" + "a" * 64}
        mock_w3.eth.wait_for_transaction_receipt.side_effect = [
            TransactionNotFound("Transaction pending"),
            receipt_obj
        ]
        mock_w3.eth.get_transaction_receipt.return_value = receipt_obj
        client = BlockchainClient(
            contract_address="0x1111111111111111111111111111111111111111",
            w3=mock_w3,
            mode=BlockchainMode.LOCAL_TEST
        )
        rcpt = client._wait_for_receipt_with_backoff("0x" + "a" * 64, timeout=5)
        self.assertEqual(rcpt.get("status"), 1)

    # 28. Regression: RPC inconsistency in block lookup (blockNumber fails, blockHash succeeds)
    def test_regression_rpc_inconsistency_block_lookup(self):
        from web3.exceptions import BlockNotFound
        mock_w3 = MagicMock()
        target_block = {"number": 12345, "timestamp": 1788686746, "hash": b"\xaa" * 32}

        def get_block_side_effect(ident):
            if ident == 12345:
                raise BlockNotFound("Block with id: 12345 not found.")
            if ident == b"\xaa" * 32 or ident == "0x" + "aa" * 32:
                return target_block
            raise ValueError(f"Unknown ident: {ident}")

        mock_w3.eth.get_block.side_effect = get_block_side_effect
        client = BlockchainClient(
            contract_address="0x1111111111111111111111111111111111111111",
            w3=mock_w3,
            mode=BlockchainMode.LOCAL_TEST
        )
        res = client._get_block_with_retry(12345, block_hash=b"\xaa" * 32, max_retries=2, initial_delay=0.01)
        self.assertIsNotNone(res)
        self.assertEqual(res["timestamp"], 1788686746)

    # 29. Regression: Transaction already mined / existing on-chain
    def test_regression_transaction_already_mined(self):
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.chain_id = 84532
        mock_w3.eth.block_number = 46459500
        mock_w3.to_hex = lambda b: "0x" + (b.hex() if isinstance(b, bytes) else str(b))

        client = BlockchainClient(
            contract_address="0x1111111111111111111111111111111111111111",
            private_key="0x" + "c" * 64,
            w3=mock_w3,
            mode=BlockchainMode.LIVE_BLOCKCHAIN
        )
        client.contract = MagicMock()
        client.contract.functions.verifyEvidence.return_value.call.return_value = (
            True, 1788686746, "0xe70d301abB4E12e36FC1FD42c71E8Ebbfe0AB672"
        )
        mock_log = {
            "transactionHash": b"\x48" * 32,
            "blockNumber": 46459229
        }
        client.contract.events.EvidenceAnchored.get_logs.return_value = [mock_log]

        evidence_hash = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)
        rec = client.anchor_evidence(evidence_hash)

        self.assertEqual(rec.anchor_status, "ALREADY_ANCHORED")
        self.assertEqual(rec.blockchain_status, BlockchainReleaseStatus.LIVE_CONFIRMED)
        self.assertEqual(rec.block_number, 46459229)
        self.assertTrue(rec.transaction_hash.startswith("0x"))
        self.assertEqual(mock_w3.eth.send_raw_transaction.call_count, 0)

    # 30. Regression: Transaction already submitted recovery check
    def test_regression_transaction_already_submitted_recovery(self):
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.chain_id = 84532
        mock_w3.eth.get_code.return_value = b"\x60\x80"
        mock_w3.eth.get_balance.return_value = 10**18
        mock_w3.eth.get_transaction_count.return_value = 1
        mock_w3.eth.gas_price = 1000000
        mock_w3.eth.estimate_gas.return_value = 50000
        mock_w3.to_hex = lambda b: "0x" + (b.hex() if isinstance(b, bytes) else str(b))
        mock_w3.eth.send_raw_transaction.return_value = b"\x48" * 32

        account_mock = MagicMock()
        account_mock.address = "0xe70d301abB4E12e36FC1FD42c71E8Ebbfe0AB672"
        account_mock.sign_transaction.return_value.raw_transaction = b"\x00"
        mock_w3.eth.account.from_key.return_value = account_mock

        mock_w3.eth.wait_for_transaction_receipt.side_effect = TimeoutError("Polling timed out")
        mock_w3.eth.get_transaction_receipt.return_value = {
            "status": 1,
            "blockNumber": 46459229,
            "transactionHash": b"\x48" * 32
        }

        client = BlockchainClient(
            contract_address="0x1111111111111111111111111111111111111111",
            private_key="0x" + "c" * 64,
            w3=mock_w3,
            mode=BlockchainMode.LIVE_BLOCKCHAIN
        )
        client.contract = MagicMock()
        client.contract.functions.verifyEvidence.return_value.call.side_effect = [
            (False, 0, "0x0000000000000000000000000000000000000000"),
            (True, 1788686746, "0xe70d301abB4E12e36FC1FD42c71E8Ebbfe0AB672")
        ]

        evidence_hash = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)
        rec = client.anchor_evidence(evidence_hash, raise_on_error=False)

        self.assertEqual(rec.anchor_status, "CONFIRMED")
        self.assertEqual(rec.blockchain_status, BlockchainReleaseStatus.LIVE_CONFIRMED)
        self.assertEqual(rec.block_number, 46459229)

    # 31. Regression: Duplicate evidence handled without submitting duplicate tx
    def test_regression_duplicate_evidence_handling(self):
        client = MockBlockchainClient()
        evidence_hash = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)

        rec1 = client.anchor_evidence(evidence_hash)
        self.assertEqual(rec1.anchor_status, "CONFIRMED")
        ts1 = rec1.timestamp

        rec2 = client.anchor_evidence(evidence_hash)
        self.assertEqual(rec2.anchor_status, "ALREADY_ANCHORED")
        self.assertEqual(rec2.timestamp, ts1)
        self.assertEqual(rec2.evidence_hash, evidence_hash)

    # 32. Regression: Receipt status == 0 explicitly fails and blocks release
    def test_regression_receipt_status_0_explicitly_fails(self):
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.chain_id = 84532
        account_mock = MagicMock()
        account_mock.address = "0x2222222222222222222222222222222222222222"
        mock_w3.eth.account.from_key.return_value = account_mock
        mock_w3.eth.get_code.return_value = b"\x60\x80"
        mock_w3.eth.get_balance.return_value = 10**18
        mock_w3.eth.get_transaction_count.return_value = 0
        mock_w3.eth.gas_price = 1000000
        mock_w3.eth.estimate_gas.return_value = 50000
        mock_w3.to_hex = lambda b: "0x" + (b.hex() if isinstance(b, bytes) else str(b))
        mock_w3.eth.send_raw_transaction.return_value = b"\x01" * 32

        mock_w3.eth.wait_for_transaction_receipt.return_value = {
            "status": 0,
            "blockNumber": 12345,
            "transactionHash": b"\x01" * 32
        }

        client = BlockchainClient(
            contract_address="0x1111111111111111111111111111111111111111",
            private_key="0x" + "c" * 64,
            w3=mock_w3,
            mode=BlockchainMode.LIVE_BLOCKCHAIN
        )
        client.contract = MagicMock()
        client.contract.functions.verifyEvidence.return_value.call.return_value = (False, 0, "0x0000000000000000000000000000000000000000")

        evidence_hash = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)
        rec = client.anchor_evidence(evidence_hash, raise_on_error=False)

        self.assertEqual(rec.anchor_status, "FAILED")
        self.assertEqual(rec.blockchain_status, BlockchainReleaseStatus.STEP3_LIVE_BLOCKCHAIN_BLOCKED)
        self.assertIn("status 0", rec.error)

    # 33. Regression: Genuine successful receipt creates verified LIVE_CONFIRMED record
    def test_regression_genuine_successful_receipt(self):
        mock_w3 = MagicMock()
        mock_w3.is_connected.return_value = True
        mock_w3.eth.chain_id = 84532
        account_mock = MagicMock()
        account_mock.address = "0xe70d301abB4E12e36FC1FD42c71E8Ebbfe0AB672"
        mock_w3.eth.account.from_key.return_value = account_mock
        mock_w3.eth.get_code.return_value = b"\x60\x80"
        mock_w3.eth.get_balance.return_value = 10**18
        mock_w3.eth.get_transaction_count.return_value = 1
        mock_w3.eth.gas_price = 6000000
        mock_w3.eth.estimate_gas.return_value = 91182
        mock_w3.to_hex = lambda b: "0x" + (b.hex() if isinstance(b, bytes) else str(b))
        mock_w3.eth.send_raw_transaction.return_value = b"\x48" * 32

        mock_w3.eth.wait_for_transaction_receipt.return_value = {
            "status": 1,
            "blockNumber": 46459229,
            "blockHash": b"\x6e" * 32,
            "gasUsed": 91182,
            "transactionHash": b"\x48" * 32
        }
        mock_w3.eth.get_block.return_value = {
            "number": 46459229,
            "timestamp": 1788686746,
            "hash": b"\x6e" * 32
        }

        client = BlockchainClient(
            contract_address="0x71fcDeb36659E264716618b3E3a7C142Ff42455a",
            private_key="0x" + "c" * 64,
            w3=mock_w3,
            mode=BlockchainMode.LIVE_BLOCKCHAIN
        )
        client.contract = MagicMock()
        client.contract.functions.verifyEvidence.return_value.call.return_value = (False, 0, "0x0000000000000000000000000000000000000000")

        evidence_hash = EvidenceCanonicalizer.compute_evidence_hash(self.sample_evidence)
        rec = client.anchor_evidence(evidence_hash, raise_on_error=True)

        self.assertEqual(rec.anchor_status, "CONFIRMED")
        self.assertEqual(rec.blockchain_status, BlockchainReleaseStatus.LIVE_CONFIRMED)
        self.assertEqual(rec.block_number, 46459229)
        self.assertEqual(rec.timestamp, 1788686746)
        self.assertTrue(rec.transaction_hash.startswith("0x"))


if __name__ == "__main__":
    unittest.main()
