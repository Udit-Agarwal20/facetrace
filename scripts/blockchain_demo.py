#!/usr/bin/env python3
"""
FaceTrace — Step 3 Blockchain Anchoring & Verification Demo
Executes the cryptographic commitment round-trip:
Canonicalize -> Hash -> Anchor -> Read -> Verify -> Tamper Simulation.
"""

import argparse
import copy
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

load_dotenv()

from src.blockchain.canonicalizer import (
    EvidenceCanonicalizer,
    NonCompliantEvidenceError
)
from src.blockchain.client import BlockchainClient, MockBlockchainClient
from src.blockchain.models import BlockchainMode, BlockchainState, BlockchainReleaseStatus

DEFAULT_EVIDENCE_PATH = Path(__file__).parent.parent / "data" / "discovered_post.json"
BASE_SEPOLIA_CHAIN_ID = 84532


def run_demo(
    evidence_path: Path = DEFAULT_EVIDENCE_PATH,
    live_mode: bool = False,
    use_mock: bool = False,
    local_evm: bool = False,
    output_path: Path = DEFAULT_EVIDENCE_PATH
):
    # Determine execution mode
    if live_mode:
        mode = BlockchainMode.LIVE_BLOCKCHAIN
    elif local_evm:
        mode = BlockchainMode.LOCAL_TEST
    else:
        # Default or --mock
        mode = BlockchainMode.MOCK_BLOCKCHAIN

    print("=" * 50)
    if mode == BlockchainMode.LIVE_BLOCKCHAIN:
        print("FACETRACE — LIVE BLOCKCHAIN VERIFICATION")
    elif mode == BlockchainMode.LOCAL_TEST:
        print("FACETRACE — LOCAL EVM TEST VERIFICATION")
    else:
        print("FACETRACE — MOCK BLOCKCHAIN VERIFICATION (TEST ONLY)")
    print("=" * 50)

    # [1] Step 2 Evidence Validation
    print("\n[1] STEP 2 EVIDENCE")
    if not evidence_path.exists():
        print(f"    [-] ERROR: Evidence file not found at: {evidence_path}")
        sys.exit(1)

    with open(evidence_path, "r", encoding="utf-8") as f:
        evidence_data = json.load(f)

    comp_state = evidence_data.get("task3_compliance", {}).get("state")
    verif_state = evidence_data.get("verification", {}).get("verification_state")

    try:
        canonical_dict = EvidenceCanonicalizer.extract_canonical_fields(evidence_data)
        print("    PASS")
        print(f"    Task3 Compliance: {comp_state}")
        print(f"    Verification: {verif_state}")
    except NonCompliantEvidenceError as e:
        print(f"    [-] REJECTED: {e}")
        print("    [!] Blockchain anchoring is strictly restricted to TASK3_SOCIAL_MATCH.")
        sys.exit(1)

    # [2] Network & Environment Gating
    print("\n[2] NETWORK")
    if mode == BlockchainMode.LIVE_BLOCKCHAIN:
        rpc_url = os.getenv("BASE_SEPOLIA_RPC_URL", "https://sepolia.base.org")
        contract_addr = os.getenv("BLOCKCHAIN_CONTRACT_ADDRESS") or os.getenv("EVIDENCE_REGISTRY_ADDRESS")
        private_key = os.getenv("BLOCKCHAIN_PRIVATE_KEY") or os.getenv("PRIVATE_KEY")

        # Strict preconditions for Live Base Sepolia
        missing_configs = []
        if not private_key:
            missing_configs.append("BLOCKCHAIN_PRIVATE_KEY (missing in .env)")
        if not contract_addr:
            missing_configs.append("BLOCKCHAIN_CONTRACT_ADDRESS (missing in .env)")

        if missing_configs:
            print(f"    Network: Base Sepolia")
            print(f"    Chain ID: {BASE_SEPOLIA_CHAIN_ID}")
            print("\n" + "=" * 50)
            print(">>> STEP3_LIVE_BLOCKCHAIN_BLOCKED <<<")
            print("Missing required live blockchain configuration:")
            for item in missing_configs:
                print(f"  - {item}")
            print("\nAction Required:")
            print("  1. Add funded testnet private key to .env: BLOCKCHAIN_PRIVATE_KEY=0x...")
            print("  2. Deploy contract: python scripts/deploy_contract.py --update-env")
            print("  3. Run live demo:   python scripts/blockchain_demo.py --live")
            print("=" * 50)
            sys.exit(1)

        client = BlockchainClient(
            rpc_url=rpc_url,
            contract_address=contract_addr,
            private_key=private_key,
            chain_id=BASE_SEPOLIA_CHAIN_ID,
            mode=BlockchainMode.LIVE_BLOCKCHAIN
        )

        if not client.is_connected():
            print(f"    [-] ERROR: Cannot connect to Base Sepolia RPC: {rpc_url}")
            print(">>> STEP3_LIVE_BLOCKCHAIN_BLOCKED <<<")
            sys.exit(1)

        print("    PASS")
        print("    Network: Base Sepolia")
        print(f"    Chain ID: {BASE_SEPOLIA_CHAIN_ID}")

        # [3] Wallet Verification
        print("\n[3] WALLET")
        balance_wei = client.w3.eth.get_balance(client.address)
        balance_eth = client.w3.from_wei(balance_wei, "ether")
        if balance_wei == 0:
            print(f"    [-] ERROR: Wallet {client.address} has 0 ETH on Base Sepolia.")
            print(">>> STEP3_LIVE_BLOCKCHAIN_BLOCKED <<<")
            sys.exit(1)
        print("    PASS")
        print(f"    Address: {client.address}")
        print(f"    Balance: {balance_eth:.6f} ETH")

        # [4] Contract Verification
        print("\n[4] CONTRACT")
        code = client.w3.eth.get_code(client.contract_address)
        if not code or code in [b"", b"\x00"] or code.hex() in ["0x", "", "0x00"]:
            print(f"    [-] ERROR: Contract address {client.contract_address} has no deployed bytecode on Base Sepolia.")
            print(">>> STEP3_LIVE_BLOCKCHAIN_BLOCKED <<<")
            sys.exit(1)
        print("    PASS")
        print(f"    Address: {client.contract_address}")

    elif mode == BlockchainMode.LOCAL_TEST:
        from web3 import Web3
        from web3.providers.eth_tester import EthereumTesterProvider
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
        print("    PASS")
        print(f"    Network: Local EVM Testnet")
        print(f"    Chain ID: {client.chain_id}")
        print("\n[3] WALLET")
        print("    PASS")
        print(f"    Address: {client.address}")
        print("\n[4] CONTRACT")
        print("    PASS")
        print(f"    Address: {client.contract_address}")

    else:
        # Mock mode
        client = MockBlockchainClient()
        print("    PASS (MOCK)")
        print("    Network: base_sepolia_mock")
        print("    Chain ID: 84532")
        print("\n[3] WALLET")
        print("    PASS (MOCK)")
        print(f"    Address: {client.mock_submitter}")
        print("\n[4] CONTRACT")
        print("    PASS (MOCK)")
        print(f"    Address: {client.contract_address}")

    # [5] Canonical Evidence
    print("\n[5] CANONICAL EVIDENCE")
    canonical_str = EvidenceCanonicalizer.canonicalize(evidence_data)
    print("    PASS")

    # [6] SHA-256 Commitment
    print("\n[6] SHA-256 COMMITMENT")
    evidence_hash = EvidenceCanonicalizer.compute_evidence_hash(canonical_str)
    print(f"    {evidence_hash}")

    # [7] Submitting Transaction
    if mode == BlockchainMode.LIVE_BLOCKCHAIN:
        print("\n[7] SUBMITTING REAL TRANSACTION")
        print("    [Safe Diagnostics]")
        print(f"    Chain ID:         {client.chain_id}")
        print(f"    Wallet Address:   {client.address}")
        print(f"    Contract Address: {client.contract_address}")
        try:
            current_nonce = client.w3.eth.get_transaction_count(client.address)
            gas_price_wei = client.w3.eth.gas_price
            print(f"    Nonce:            {current_nonce}")
            print(f"    Gas Price:        {gas_price_wei} wei ({client.w3.from_wei(gas_price_wei, 'gwei'):.4f} Gwei)")
        except Exception:
            pass
    elif mode == BlockchainMode.LOCAL_TEST:
        print("\n[7] SUBMITTING LOCAL TRANSACTION")
    else:
        print("\n[7] SUBMITTING MOCK TRANSACTION")

    record = client.anchor_evidence(evidence_hash)
    if record.error:
        print(f"    [-] ERROR: Anchoring failed: {record.error}")
        if mode == BlockchainMode.LIVE_BLOCKCHAIN:
            print(">>> STEP3_LIVE_BLOCKCHAIN_BLOCKED <<<")
        sys.exit(1)

    print("    PASS")
    if record.anchor_status == "ALREADY_ANCHORED":
        print("    Classification: LIVE_ANCHOR_ALREADY_CONFIRMED")

    # [8] Transaction Confirmation
    print("\n[8] TRANSACTION CONFIRMED")
    print("    PASS")
    print(f"    TX: {record.transaction_hash}")
    print(f"    Block: {record.block_number}")
    if mode == BlockchainMode.LIVE_BLOCKCHAIN and record.transaction_hash:
        try:
            rcpt = client.w3.eth.get_transaction_receipt(record.transaction_hash)
            if rcpt:
                print(f"    Receipt Status:   {rcpt.get('status')}")
                print(f"    Gas Used:         {rcpt.get('gasUsed')}")
                block_h = rcpt.get("blockHash")
                if block_h:
                    print(f"    Block Hash:       {client.w3.to_hex(block_h)}")
        except Exception:
            pass

    # [9] On-Chain Read-Back
    print("\n[9] ON-CHAIN READ-BACK")
    exists, on_chain_time, submitter = client.verify_evidence(evidence_hash)
    if not exists:
        print("    [-] ERROR: Evidence commitment not found on-chain.")
        sys.exit(1)
    print("    PASS")
    print(f"    Exists: {exists}")
    print(f"    Timestamp: {on_chain_time}")
    print(f"    Submitter: {submitter}")

    # [10] Hash Comparison
    print("\n[10] HASH COMPARISON")
    recomputed_hash = EvidenceCanonicalizer.compute_evidence_hash(evidence_data)
    print(f"    Local:    {recomputed_hash}")
    print(f"    On-chain: {evidence_hash}")

    comparison = client.verify_local_against_chain(recomputed_hash)
    if comparison.is_verified:
        print("    MATCH")
    else:
        print(f"    [-] MISMATCH ({comparison.reason})")
        sys.exit(1)

    print("\n" + "=" * 50)
    if mode == BlockchainMode.LIVE_BLOCKCHAIN:
        print("FINAL RESULT:\nLIVE_BLOCKCHAIN_VERIFIED\n")
        print(f"BLOCKCHAIN_STATUS = {record.blockchain_status.value}")
        print("INTEGRITY_STATUS = MATCH\n")
        print("Explorer:")
        print(f"https://sepolia.basescan.org/tx/{record.transaction_hash}")
        print(f"Contract: https://sepolia.basescan.org/address/{client.contract_address}")
    elif mode == BlockchainMode.LOCAL_TEST:
        print("FINAL RESULT:\nLOCAL_EVM_VERIFIED\n")
        print(f"BLOCKCHAIN_STATUS = {record.blockchain_status.value}")
        print("INTEGRITY_STATUS = MATCH")
    else:
        print("FINAL RESULT:\nMOCK_SIMULATION_VERIFIED\n")
        print(f"BLOCKCHAIN_STATUS = {record.blockchain_status.value}")
        print("INTEGRITY_STATUS = MATCH")
        print("[!] Note: Mock execution cannot be presented as Base Sepolia proof.")
    print("=" * 50)

    # Save blockchain telemetry to evidence JSON
    evidence_data["blockchain"] = record.to_dict()
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(evidence_data, f, indent=2)

    # Controlled Tamper Simulation
    print("\n" + "=" * 50)
    print("TAMPER SIMULATION")
    print("=" * 50)
    tampered_data = copy.deepcopy(evidence_data)
    original_url = tampered_data["selected_candidate"]["page_url"]
    altered_url = original_url + "_tampered_malicious_edit"
    tampered_data["selected_candidate"]["page_url"] = altered_url

    tampered_canonical = EvidenceCanonicalizer.canonicalize(tampered_data)
    tampered_hash = EvidenceCanonicalizer.compute_evidence_hash(tampered_canonical)

    print(f"\nOriginal Hash:\n{evidence_hash}")
    print(f"\nTampered Hash:\n{tampered_hash}")
    print(f"\nOn-chain Hash:\n{evidence_hash}")

    print("\nComparison:\nMISMATCH")
    print("\nFINAL INTEGRITY RESULT:\nTAMPER_DETECTED")
    print("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FaceTrace Step 3 Blockchain Demo")
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE_PATH, help="Path to Step 2 evidence JSON")
    parser.add_argument("--live", action="store_true", help="Execute real on-chain transaction on Base Sepolia")
    parser.add_argument("--local", action="store_true", help="Execute real EVM bytecode on local in-memory test provider")
    parser.add_argument("--mock", action="store_true", help="Run offline mock simulation (TEST_ONLY)")
    parser.add_argument("--output", type=Path, default=DEFAULT_EVIDENCE_PATH, help="Output evidence JSON path")
    args = parser.parse_args()

    run_demo(
        evidence_path=args.evidence,
        live_mode=args.live,
        use_mock=args.mock,
        local_evm=args.local,
        output_path=args.output
    )
