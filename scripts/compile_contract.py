#!/usr/bin/env python3
"""
FaceTrace — Contract Compiler
Compiles EvidenceRegistry.sol using py-solc-x and produces contracts/EvidenceRegistry.json.
"""

import json
from pathlib import Path
import solcx

CONTRACT_DIR = Path(__file__).parent.parent / "contracts"
SOLIDITY_FILE = CONTRACT_DIR / "EvidenceRegistry.sol"
OUTPUT_FILE = CONTRACT_DIR / "EvidenceRegistry.json"
SOLC_VERSION = "0.8.20"


def compile_evidence_registry():
    print(f"[*] Ensuring solc {SOLC_VERSION} is installed...")
    installed_versions = solcx.get_installed_solc_versions()
    if not any(str(v).startswith(SOLC_VERSION) for v in installed_versions):
        solcx.install_solc(SOLC_VERSION)

    solcx.set_solc_version(SOLC_VERSION)
    print(f"[*] Compiling {SOLIDITY_FILE.name}...")

    compiled = solcx.compile_files(
        [str(SOLIDITY_FILE)],
        output_values=["abi", "bin", "bin-runtime"],
        solc_version=SOLC_VERSION
    )

    matching_keys = [k for k in compiled.keys() if k.endswith(":EvidenceRegistry")]
    if not matching_keys:
        raise RuntimeError(f"Contract EvidenceRegistry not found in compilation results: {list(compiled.keys())}")

    contract_data = compiled[matching_keys[0]]
    artifact = {
        "contractName": "EvidenceRegistry",
        "abi": contract_data["abi"],
        "bytecode": contract_data["bin"],
        "deployedBytecode": contract_data["bin-runtime"],
        "solcVersion": SOLC_VERSION
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2)

    print(f"[+] Successfully compiled EvidenceRegistry!")
    print(f"    - ABI functions: {len([x for x in artifact['abi'] if x.get('type') == 'function'])}")
    print(f"    - Bytecode size: {len(artifact['bytecode']) // 2} bytes")
    print(f"    - Output saved to: {OUTPUT_FILE}")
    return artifact


if __name__ == "__main__":
    compile_evidence_registry()
