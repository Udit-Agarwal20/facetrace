#!/usr/bin/env python3
"""
FaceTrace — Deploy EvidenceRegistry to Base Sepolia
Deploys the minimal EvidenceRegistry smart contract to Base Sepolia (Chain ID: 84532).
"""

import argparse
import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from web3 import Web3

load_dotenv()

DEFAULT_RPC = "https://sepolia.base.org"
BASE_SEPOLIA_CHAIN_ID = 84532
CONTRACT_ARTIFACT_PATH = Path(__file__).parent.parent / "contracts" / "EvidenceRegistry.json"


def deploy(rpc_url: str = None, private_key: str = None, update_env: bool = False):
    rpc = rpc_url or os.getenv("BASE_SEPOLIA_RPC_URL") or DEFAULT_RPC
    pk = private_key or os.getenv("BLOCKCHAIN_PRIVATE_KEY") or os.getenv("PRIVATE_KEY")

    if not pk:
        print("[!] ERROR: Missing private key.")
        print("    Please set BLOCKCHAIN_PRIVATE_KEY or PRIVATE_KEY in your .env file.")
        print("    Ensure the account has Base Sepolia testnet ETH (e.g. from https://faucets.chain.link or https://base.org/faucets).")
        sys.exit(1)

    pk = pk.strip()
    if not pk.startswith("0x") and len(pk) == 64:
        pk = "0x" + pk

    if not CONTRACT_ARTIFACT_PATH.exists():
        print("[*] Contract artifact not found. Compiling...")
        from scripts.compile_contract import compile_evidence_registry
        compile_evidence_registry()

    with open(CONTRACT_ARTIFACT_PATH, "r", encoding="utf-8") as f:
        artifact = json.load(f)

    abi = artifact["abi"]
    bytecode = artifact["bytecode"]

    w3 = Web3(Web3.HTTPProvider(rpc))
    if not w3.is_connected():
        print(f"[!] ERROR: Cannot connect to RPC: {rpc}")
        sys.exit(1)

    chain_id = w3.eth.chain_id
    if chain_id != BASE_SEPOLIA_CHAIN_ID:
        print(f"[!] WARNING: Target chain ID is {chain_id}, expected Base Sepolia ({BASE_SEPOLIA_CHAIN_ID})")

    account = w3.eth.account.from_key(pk)
    balance_wei = w3.eth.get_balance(account.address)
    balance_eth = w3.from_wei(balance_wei, "ether")

    print("=" * 80)
    print("         FACETRACE — BASE SEPOLIA CONTRACT DEPLOYER")
    print("=" * 80)
    print(f"Network:          Base Sepolia (Chain ID: {chain_id})")
    print(f"RPC Endpoint:     {rpc}")
    print(f"Deployer Address: {account.address}")
    print(f"Deployer Balance: {balance_eth:.6f} ETH")

    if balance_wei == 0:
        print(f"[!] ERROR: Deployer balance is 0 ETH. Please fund {account.address} with Base Sepolia testnet ETH.")
        sys.exit(1)

    print("\n[*] Preparing deployment transaction...")
    EvidenceRegistry = w3.eth.contract(abi=abi, bytecode=bytecode)
    nonce = w3.eth.get_transaction_count(account.address, "pending")
    gas_price = w3.eth.gas_price

    construct_txn = EvidenceRegistry.constructor().build_transaction({
        "chainId": chain_id,
        "from": account.address,
        "nonce": nonce,
        "gasPrice": gas_price
    })

    try:
        est_gas = w3.eth.estimate_gas(construct_txn)
        construct_txn["gas"] = int(est_gas * 1.2)
    except Exception as e:
        print(f"[!] Gas estimation note: {e}, using 800,000 gas limit.")
        construct_txn["gas"] = 800000

    print("[*] Signing and submitting deployment transaction...")
    signed_tx = account.sign_transaction(construct_txn)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_hash_hex = w3.to_hex(tx_hash)
    print(f"[+] Deployment submitted! Transaction Hash: {tx_hash_hex}")
    print(f"    View on BaseScan: https://sepolia.basescan.org/tx/{tx_hash_hex}")

    print("[*] Waiting for confirmation (up to 60 seconds)...")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

    if receipt.get("status") != 1:
        print("[!] ERROR: Transaction failed on-chain.")
        sys.exit(1)

    contract_address = receipt.get("contractAddress")
    print(f"\n[+] CONTRACT DEPLOYED SUCCESSFULLY!")
    print(f"    Address:          {contract_address}")
    print(f"    Block Number:     {receipt.get('blockNumber')}")
    print(f"    Gas Used:         {receipt.get('gasUsed')}")
    print(f"    BaseScan URL:     https://sepolia.basescan.org/address/{contract_address}")

    if update_env:
        env_file = Path(__file__).parent.parent / ".env"
        if env_file.exists():
            content = env_file.read_text(encoding="utf-8")
            if "BLOCKCHAIN_CONTRACT_ADDRESS=" in content:
                import re
                content = re.sub(r"BLOCKCHAIN_CONTRACT_ADDRESS=.*", f"BLOCKCHAIN_CONTRACT_ADDRESS={contract_address}", content)
            else:
                content += f"\nBLOCKCHAIN_CONTRACT_ADDRESS={contract_address}\n"
            env_file.write_text(content, encoding="utf-8")
            print(f"[+] Updated .env with BLOCKCHAIN_CONTRACT_ADDRESS={contract_address}")

    print("\nNext step: Run the blockchain demo with:")
    print(f"python scripts/blockchain_demo.py --evidence data/discovered_post.json")
    return contract_address


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy EvidenceRegistry to Base Sepolia")
    parser.add_argument("--rpc", help="Base Sepolia RPC URL")
    parser.add_argument("--private-key", help="Deployer private key")
    parser.add_argument("--update-env", action="store_true", help="Automatically write contract address to .env")
    args = parser.parse_args()

    deploy(rpc_url=args.rpc, private_key=args.private_key, update_env=args.update_env)
