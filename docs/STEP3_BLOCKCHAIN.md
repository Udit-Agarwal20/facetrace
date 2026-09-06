# Step 3 — Blockchain Evidence Anchoring & Verification Architecture
**FaceTrace — Discover. Verify. Anchor.**  
**Hacker House Goa 2026 — Task 3**

---

## 1. Why Blockchain is Used

In digital forensic discovery and facial verification, a common point of failure is data tampering after discovery:
- Evidence files on local servers can be modified after the fact.
- URLs, facial similarity scores, or image hashes can be maliciously inflated or altered.
- Centralized databases cannot provide verifiable public timestamps without trusted third parties.

**FaceTrace uses blockchain to anchor an immutable, publicly verifiable cryptographic commitment to the discovered evidence.**
- **The blockchain does not prove that a person is guilty or who they are.**
- **The blockchain proves that the specific discovered evidence package existed at a specific point in time and has not been altered since.**

---

## 2. What Exactly is Stored on Blockchain

The smart contract stores only a minimal, gas-efficient, privacy-preserving commitment:

```solidity
struct EvidenceRecord {
    bytes32 evidenceHash; // SHA-256 digest of canonical evidence
    uint256 timestamp;    // Block timestamp of inclusion
    address submitter;    // Submitting wallet address
    bool exists;          // Record existence flag
}
```

- **Gas footprint**: Single SSTORE slot write (~45,000 gas).
- **Data size**: 32 bytes (`bytes32`).

---

## 3. What is Deliberately NOT Stored on Blockchain

Under strict **privacy-by-design** principles:
- **NO raw images**: Never upload query or candidate images to the blockchain.
- **NO biometric embeddings**: ArcFace 512-dimensional vector embeddings are never published on-chain.
- **NO personal data**: Names, personal identities, and sensitive user information are excluded.
- **NO private keys or RPC credentials**: Secrets reside exclusively in `.env` and are never committed or logged.

---

## 4. Deterministic Canonical Evidence Format

To guarantee that the exact same evidence always produces the exact same hash regardless of language, platform, or dictionary ordering:

### Stable Field Selection
Only deterministic fields necessary to prove the discovery and verification are extracted:
1. `schema_version`: e.g. `"1.0"`
2. `discovery_type`: e.g. `"image_provenance"`
3. `verification_type`: e.g. `"VERIFIED_EXACT"`
4. `task3_compliance`: e.g. `"TASK3_SOCIAL_MATCH"`
5. `candidate_url`: URL of the discovered post
6. `candidate_image_url`: Direct URL of the retrieved candidate image
7. `platform`: e.g. `"reddit"`, `"youtube"`
8. `candidate_image_sha256`: SHA-256 byte digest of the retrieved candidate image
9. `candidate_image_phash`: Perceptual hash distance integer
10. `face_similarity`: ArcFace cosine similarity rounded to 4 decimal places
11. `execution_mode`: e.g. `"LIVE_EXTERNAL_SEARCH"`

### Serialization Rules
- Keys are sorted alphabetically (`sort_keys=True`).
- Whitespace is eliminated with compact separators (`separators=(',', ':')`).
- Encoded as UTF-8 bytes.

### Example Canonical JSON String
```json
{"candidate_image_phash":0,"candidate_image_sha256":"f8f141c421f4e52cc7255bc3741572659478a60b59ffe1fc888802661efc8e5e","candidate_image_url":"http://allthingsd.com/files/2012/08/Barack-Obama-Reddit.jpeg","candidate_url":"https://www.reddit.com/r/southpaws/comments/z1yuo/i_knew_obama_was_a_lefty_but_im_surprised_he","discovery_type":"image_provenance","execution_mode":"LIVE_EXTERNAL_SEARCH","face_similarity":1.0,"platform":"reddit","schema_version":"1.0","task3_compliance":"TASK3_SOCIAL_MATCH","verification_type":"VERIFIED_EXACT"}
```

---

## 5. SHA-256 Commitment Generation

```text
canonical_json (UTF-8 bytes)
          ↓
SHA-256 Hash Function
          ↓
0x1f2e49a7c034d578add5b8bb4e307fdc0b50c7ba67dad5dc0e04a1b45c244f4d (bytes32)
```

Any modification to any field—even changing a single character in the candidate URL or altering the face similarity score from `1.0` to `0.9999`—produces a completely different hash digest, invalidating on-chain verification.

---

## 6. Smart Contract Design

Contract: `contracts/EvidenceRegistry.sol`
```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract EvidenceRegistry {
    struct EvidenceRecord {
        bytes32 evidenceHash;
        uint256 timestamp;
        address submitter;
        bool exists;
    }

    mapping(bytes32 => EvidenceRecord) public records;

    event EvidenceAnchored(
        bytes32 indexed evidenceHash,
        uint256 timestamp,
        address indexed submitter
    );

    function anchorEvidence(bytes32 evidenceHash) external {
        require(evidenceHash != bytes32(0), "Invalid evidence hash");
        require(!records[evidenceHash].exists, "Evidence already anchored");

        records[evidenceHash] = EvidenceRecord({
            evidenceHash: evidenceHash,
            timestamp: block.timestamp,
            submitter: msg.sender,
            exists: true
        });

        emit EvidenceAnchored(evidenceHash, block.timestamp, msg.sender);
    }

    function verifyEvidence(bytes32 evidenceHash)
        external
        view
        returns (bool exists, uint256 timestamp, address submitter)
    {
        EvidenceRecord memory rec = records[evidenceHash];
        return (rec.exists, rec.timestamp, rec.submitter);
    }
}
```

---

## 7. Base Sepolia Configuration

- **Network Name**: Base Sepolia
- **Chain ID**: `84532`
- **RPC Endpoint**: `https://sepolia.base.org` (or managed via Alchemy / Infura / QuickNode)
- **Explorer**: [https://sepolia.basescan.org](https://sepolia.basescan.org)
- **Testnet Faucets**:
  - [Base Network Faucet](https://base.org/faucets)
  - [Chainlink Base Sepolia Faucet](https://faucets.chain.link)

Environment Variables in `.env`:
```ini
BASE_SEPOLIA_RPC_URL=https://sepolia.base.org
BLOCKCHAIN_CONTRACT_ADDRESS=0x...
BLOCKCHAIN_PRIVATE_KEY=0x...
```

---

## 8. Anchoring Workflow

```text
Step 2 Output (`data/discovered_post.json`)
      │
      ▼
Task 3 Compliance Gate Check:
  - Is compliance state == TASK3_SOCIAL_MATCH?
  - Is verification state in {VERIFIED_EXACT, VERIFIED_DERIVATIVE, VERIFIED_FACE_MATCH}?
      │
      ▼
Extract Stable Canonical Representation
      │
      ▼
Compute SHA-256 -> bytes32 evidenceHash
      │
      ▼
Submit `anchorEvidence(evidenceHash)` transaction on Base Sepolia
      │
      ▼
Await confirmation receipt (gas ~45,000, 1 confirmation)
      │
      ▼
Update `data/discovered_post.json` with blockchain receipt metadata
```

---

## 9. Re-Verification Workflow

Anyone with the off-chain evidence file can independently verify it at any future date:
1. Load off-chain evidence JSON.
2. Canonicalize using `EvidenceCanonicalizer.canonicalize()`.
3. Compute local SHA-256 hash ($H_{local}$).
4. Query smart contract `verifyEvidence(H_{local})` on Base Sepolia.
5. If `exists == true` and $H_{local} == H_{chain}$:
   - **Decision**: `BLOCKCHAIN_VERIFIED` (`MATCH`).
6. If `exists == false`:
   - **Decision**: `VERIFICATION_FAIL` (Record does not exist or has been tampered with).

---

## 10. Tamper Detection Demonstration

If an attacker modifies any field in the evidence file (for example, replacing the social post URL or claiming higher face similarity):
```text
Original Evidence Hash (H1): 0x1f2e49a7c034d578add5b8bb4e307fdc0b50c7ba67dad5dc0e04a1b45c244f4d
Tampered Evidence Hash (H2): 0x104fffc5895da86afd10df5597f79b325b90690ecb58a0a1a92ab102546b34f5
On-Chain Anchored Hash (H1): 0x1f2e49a7c034d578add5b8bb4e307fdc0b50c7ba67dad5dc0e04a1b45c244f4d

Comparison:
H2 != H1  ==>  TAMPER_DETECTED
```

---

## 11. Failure Modes & Recovery

| Failure Mode | Detection | Handling Strategy |
|---|---|---|
| **RPC Unavailable** | HTTP / Socket connection error | Client returns `BlockchainState.BLOCKCHAIN_ERROR` with explicit diagnostics. Does not fail silently. |
| **Insufficient Gas** | `gas_price * gas > balance` | Explicit error indicating deployer balance is 0 with faucet links. |
| **Duplicate Evidence** | `records[evidenceHash].exists == true` | Contract reverts `"Evidence already anchored"`. Client detects pre-existing commitment and marks `ALREADY_ANCHORED` with original timestamp. |
| **Non-Compliant Evidence** | State is `WEB_MATCH_ONLY` or `REJECTED` | `NonCompliantEvidenceError` raised. Gated at entry before transaction creation. |
| **Invalid Evidence Hash** | Hash length != 66 or missing `0x` | `ValueError` raised immediately before network transmission. |

---

## 12. Security & Privacy Decisions

1. **Zero Raw Biometrics**: No face images or vector embeddings are stored on-chain.
2. **Secrets Protection**: Private keys and RPC secrets are read from environment variables only. The test suite explicitly asserts that private keys never appear in log streams, exception messages, or evidence JSON payloads.
3. **Immutability Scope**: Immutability applies to the cryptographic commitment, not the identity of the person.

---

---

## 13. Verification Modes & Release Statuses

FaceTrace enforces a strict anti-false-pass architecture that explicitly distinguishes three execution tiers. Offline or simulated proofs are never mislabeled as live blockchain proofs.

```
+-----------------------------------------------------------------------------------------------+
|                                    FACETRACE VERIFICATION TIERS                               |
+--------------------------+----------------------------+---------------------------------------+
| 1. Local EVM Test        | 2. Mock Verification       | 3. Live Base Sepolia Proof            |
| Status: LOCAL_TEST       | Status: TEST_ONLY          | Status: LIVE_CONFIRMED                |
+--------------------------+----------------------------+---------------------------------------+
| Provider: eth_tester     | Provider: In-memory store  | Network: Base Sepolia Public Testnet  |
| Bytecode: Real Solidity  | Bytecode: None             | Chain ID: 84532                       |
| Network-independent      | Network-independent        | Requires: Funded wallet, RPC in .env  |
| NEVER public proof       | NEVER public proof         | Publicly verifiable on BaseScan       |
+--------------------------+----------------------------+---------------------------------------+
```

### 1. Local EVM Test Verification (`BLOCKCHAIN_STATUS = LOCAL_TEST`)
- **Engine**: Python `EthereumTesterProvider` running real compiled EVM bytecode in memory.
- **Transactions**: Generates real transaction receipts, calculates real gas, executes constructor and methods.
- **Scope**: Used for automated regression testing (`test_blockchain_anchoring.py`).
- **Rule**: Cannot be classified as Base Sepolia or `LIVE_CONFIRMED`.

### 2. Mock Verification (`BLOCKCHAIN_STATUS = TEST_ONLY`)
- **Engine**: `MockBlockchainClient` in-memory dictionary store.
- **Transactions**: Synthetic transaction hashes (`0xmocktx...`).
- **Scope**: Offline development and CLI demo testing when no network is available.
- **Rule**: Outputs `BLOCKCHAIN_STATUS = TEST_ONLY`. Must NEVER be reported as a verifiable public proof.

### 3. Live Base Sepolia Verification (`BLOCKCHAIN_STATUS = LIVE_CONFIRMED`)
- **Engine**: `BlockchainClient` interacting directly with public Base Sepolia testnet RPC (`chainId: 84532`).
- **Contract**: Real deployed `EvidenceRegistry.sol` contract address verified on-chain.
- **Transactions**: Real transaction broadcast to Base Sepolia, mined into an immutable block, and retrievable on BaseScan.
- **Gating**: If any credential (RPC, private key, contract address, testnet ETH) is missing, system fails explicitly with `STEP3_LIVE_BLOCKCHAIN_BLOCKED`. Silently substituting mocks is strictly forbidden.

---

## 14. Running Automated Tests

```bash
# Run Step 3 blockchain anchoring unit test suite (24 tests, network-independent)
.venv/bin/python -m unittest tests/test_blockchain_anchoring.py -v

# Run all test suites across the repository (39 tests)
.venv/bin/python -m unittest discover -s tests -v

# Run live Base Sepolia smoke test (strictly requires funded wallet and contract in .env)
RUN_LIVE_BLOCKCHAIN_TESTS=1 .venv/bin/python -m unittest tests/test_live_base_sepolia.py -v
```

---

## 15. Running the Blockchain Demos

```bash
# 1. Mock demo (offline simulation, outputs TEST_ONLY)
.venv/bin/python scripts/blockchain_demo.py --mock

# 2. Local EVM test demo (real Solidity execution in memory, outputs LOCAL_TEST)
.venv/bin/python scripts/blockchain_demo.py --local

# 3. Deploy EvidenceRegistry contract to Base Sepolia (requires BLOCKCHAIN_PRIVATE_KEY in .env)
.venv/bin/python scripts/deploy_contract.py --update-env

# 4. Live Base Sepolia verification (requires deployed contract and funded wallet)
.venv/bin/python scripts/blockchain_demo.py --live
```
