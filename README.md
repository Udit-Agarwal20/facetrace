# FaceTrace — Verifiable Face-Match Evidence
**Hacker House Goa 2026 — Task 3**
**VERIFY → ANCHOR → PROVE**

## Step 5 Status: `STEP5_COMPLETE`
> **Hackathon Presentation & Reliability Status**: Step 1 (Biometric Face Engine), Step 2 (Google Vision Reverse Discovery & Multi-Level Verification), Step 3 (Base Sepolia Smart Contract Anchoring), and Step 4 (Master End-to-End Orchestrator) are **FROZEN & HARDENED**.
> Step 5 adds a **Forensic Evidence Workstation Web UI** designed specifically for hackathon judging.
> **Judge UX Guarantees**: Zero MetaMask requirement, zero wallet configuration, zero gas setup, and zero CLI commands needed during judging.

---

## Canonical Judge Presentation Command

Launch the judge-facing workstation web interface with one command:

```bash
python scripts/run_facetrace.py --ui
```
*or alternatively:*
```bash
python scripts/serve_ui.py
```

Then open `http://127.0.0.1:8000` in any desktop browser (1440px, 1280px, 1024px).

### Judging Flow (Under 10 Seconds to Understand):
1. **Screen 1 (Input & Consent)**: Select consented benchmark face specimen (e.g., Barack Obama AMA, Task 3 verified). Confirm explicit consent notice (PRD FR-01).
2. **Click "VERIFY FACE"**: Dispatches deterministic pipeline without exposing wallet or backend keys.
3. **Screen 2 (Chronological Pipeline)**: Watch real-time stage states (`PENDING` → `RUNNING` → `PASSED`) across 7 forensic checkpoints.
4. **Screen 3 (Discovery Result)**: Inspect discovered Reddit social post candidate, `IMAGE PROVENANCE`, and `TASK3_SOCIAL_MATCH`.
5. **Screen 4 (Forensic Evidence Matrix)**: Review 4-layer verification ladder (SHA-256 exact match, pHash hamming distance, ArcFace 512-dim cosine similarity, and social post platform gate).
6. **Screen 5 (Blockchain Proof)**: Inspect on-chain registration on Base Sepolia (`chainId: 84532`, contract `0x71fc...455a`, transaction `0x48e3...77d7`). Click **"VIEW ON BASESCAN"** to view the live transaction directly on BaseScan block explorer.
7. **Screen 6 (Integrity & Tamper Demo)**: Inspect cryptographic proof comparing original evidence hash ($H_1 = \text{ON-CHAIN}$) with malicious edit ($H_2 \ne \text{ON-CHAIN} \implies \text{TAMPER DETECTED}$).
8. **Screen 7 (Final Summary Bar)**: Verify 6 checkmarks and click **"NEW VERIFICATION"** to cleanly reset the workstation for another evaluation.

---

## Canonical CLI Quick-Start Path (Command-Line Evaluation)

If evaluating via terminal:

### 1. Configure `.env`
Ensure your `.env` contains:
```ini
# Base Sepolia RPC & Smart Contract Configuration
BASE_SEPOLIA_RPC_URL=https://sepolia.base.org
BLOCKCHAIN_CHAIN_ID=84532
BLOCKCHAIN_CONTRACT_ADDRESS=0x71fcDeb36659E264716618b3E3a7C142Ff42455a
BLOCKCHAIN_PRIVATE_KEY=your_base_sepolia_private_key

# Google Cloud Vision Credentials
GOOGLE_APPLICATION_CREDENTIALS=/path/to/google_cloud_credentials.json
```

### 2. Run Canonical Master Command
```bash
python scripts/run_facetrace.py --live
```

### 3. Observe Judge-Facing Screen Recording Output
```text
==================================================
FACETRACE
VERIFY → ANCHOR → PROVE
==================================================
[1] FACE INPUT
    PASS

[2] FACE DETECTION
    PASS
    Faces detected: 1

[3] LIVE WEB SEARCH
    PASS
    Provider: Google Cloud Vision

[4] SOCIAL POST DISCOVERY
    PASS
    Platform: Reddit

[5] INDEPENDENT VERIFICATION
    PASS
    Face similarity: 1.0000
    Verification: VERIFIED_EXACT

[6] TASK 3 COMPLIANCE
    PASS
    TASK3_SOCIAL_MATCH

[7] EVIDENCE COMMITMENT
    PASS
    SHA-256: 0x1f2e49a7c034d578add5b8bb4e307fdc0b50c7ba67dad5dc0e04a1b45c244f4d

[8] BLOCKCHAIN
    PASS
    Network: Base Sepolia
    Contract: 0x71fcDeb36659E264716618b3E3a7C142Ff42455a
    Transaction: 0x48e3b99c03504f08005eaf60a25073e76ad75401e310c50f27fbd208275077d7
    Anchor Mode: EXISTING_RECOVERY

[9] ON-CHAIN VERIFICATION
    PASS
    Local hash == On-chain hash

[10] INTEGRITY TEST
    PASS
    Modified evidence detected

==================================================
FINAL RESULT
==================================================

FACE MATCH EVIDENCE VERIFIED

Blockchain:
LIVE_BLOCKCHAIN_VERIFIED
ANCHOR_MODE = EXISTING_RECOVERY

Integrity:
MATCH

Tamper Test:
TAMPER_DETECTED

Explorer:
https://sepolia.basescan.org/tx/0x48e3b99c03504f08005eaf60a25073e76ad75401e310c50f27fbd208275077d7

==================================================
```

---

## Live Base Sepolia Blockchain Deployment & Proofs

| Parameter | Value |
| :--- | :--- |
| **Network** | **Base Sepolia Testnet** |
| **Chain ID** | `84532` |
| **RPC Endpoint** | `https://sepolia.base.org` |
| **Registry Smart Contract** | [`0x71fcDeb36659E264716618b3E3a7C142Ff42455a`](https://sepolia.basescan.org/address/0x71fcDeb36659E264716618b3E3a7C142Ff42455a) |
| **Confirmed Transaction** | [`0x48e3b99c03504f08005eaf60a25073e76ad75401e310c50f27fbd208275077d7`](https://sepolia.basescan.org/tx/0x48e3b99c03504f08005eaf60a25073e76ad75401e310c50f27fbd208275077d7) |
| **Block Number** | `46459229` |
| **Receipt Status** | `1 (Success)` |
| **Canonical Evidence Hash** | `0x1f2e49a7c034d578add5b8bb4e307fdc0b50c7ba67dad5dc0e04a1b45c244f4d` |
| **Deployer / Anchor Wallet** | `0xe70d301abB4E12e36FC1FD42c71E8Ebbfe0AB672` |
| **Anchor Semantics** | Idempotent recovery (`ANCHOR_MODE = EXISTING_RECOVERY`) — confirms on-chain proof without submitting duplicate transactions |

---

## Privacy-by-Design Commitment

FaceTrace was designed from ground up with absolute biometric privacy:

1. **Zero Raw Images On-Chain**: No query photos, candidate images, or crops are ever sent to the blockchain or external RPCs.
2. **Zero Biometric Embeddings On-Chain**: ArcFace 512-dimensional vector embeddings remain strictly local on the client machine and are destroyed after verification.
3. **Cryptographic Fingerprint Only**: The smart contract stores only a 32-byte SHA-256 hash commitment (`bytes32 evidenceHash`), timestamp, and submitter address for evidence-integrity verification.
4. **No Secrets Leakage**: Private keys and GCP credentials are sanitized and never written to output logs, run JSON records, or console streams.
5. **FR-01 Subject Consent Enforcement**: Consent validation is mandatory before any reverse discovery call is initiated.

---

## Known System Boundaries & Real-World Limitations

1. **Discovery is Image Provenance, Not Universal Identity Search**:
   Google Cloud Vision Web Detection discovers indexed web pages containing identical, cropped, or derivative instances of the query image (`discovery_type: image_provenance`). FaceTrace provides **verifiable face-match evidence**, not universal cross-photo identity search across arbitrary unindexed images.
2. **Public Indexing Boundary**:
   Discovery requires that social-media posts have been indexed by public web crawlers. Content behind private profiles, walled gardens, authentication walls, or blocked by `robots.txt` cannot be indexed.
3. **Biometric Similarity Scope**:
   InsightFace ArcFace evaluates geometric facial feature similarity. Facial similarity $\ge 0.72$ confirms consistent facial geometry, not legal or authoritative government identity.
4. **Idempotent Blockchain Anchoring**:
   If an evidence package has already been committed to Base Sepolia, the pipeline automatically recovers the existing transaction proof (`ANCHOR_MODE = EXISTING_RECOVERY`) instead of attempting an erroneous duplicate re-submission.
5. **Blockchain Role**:
   The blockchain provides immutable, tamper-evident evidence-integrity verification; raw biometric data is never stored on-chain.

---

## Master Orchestration State Machine

FaceTrace transitions through an explicit 17-stage deterministic state machine:

```text
INIT
  ↓
INPUT_VALIDATED
  ↓
CONSENT_CONFIRMED
  ↓
FACE_DETECTED & FACE_EMBEDDED
  ↓
SEARCH_RUNNING → SEARCH_COMPLETE
  ↓
CANDIDATE_SELECTED
  ↓
SOCIAL_COMPLIANCE_PASSED
  ↓
FACE_VERIFICATION_PASSED
  ↓
EVIDENCE_VALIDATED → EVIDENCE_HASHED
  ↓
BLOCKCHAIN_ANCHORING → BLOCKCHAIN_CONFIRMED
  ↓
ONCHAIN_VERIFIED
  ↓
TAMPER_TEST_COMPLETE
  ↓
COMPLETE
```

### Deterministic Failure States:
- `INPUT_ERROR`: Missing or unreadable image file, or consent withheld.
- `NO_FACE`: Zero faces detected in input image.
- `SEARCH_ERROR`: External provider network timeout or API error.
- `NO_MATCH`: No candidates discovered for target image.
- `SOCIAL_REQUIREMENT_FAILED`: Candidate rejected by Task 3 social-post compliance gate.
- `FACE_VERIFICATION_FAILED`: Candidate face similarity below calibrated threshold ($< 0.72$).
- `EVIDENCE_INVALID`: Canonical evidence envelope missing required fields.
- `BLOCKCHAIN_ERROR`: RPC connection error or zero balance.
- `BLOCKCHAIN_VERIFICATION_FAILED`: Local hash does not match contract read-back hash.
- `TAMPER_DETECTED`: Tampered record verification correctly caught discrepancy.

---

## Demo Safety & Alternative Execution Modes

To ensure judges can inspect or test the codebase in any environment:

```bash
# Offline Mock Simulation (TEST ONLY — explicitly labeled)
python scripts/run_facetrace.py --mock

# Base Sepolia Dry Run (simulates on-chain transaction without gas)
python scripts/run_facetrace.py --dry-run

# Verbose Technical Diagnostics (enables full debug traces)
python scripts/run_facetrace.py --live --verbose
```

> **Anti-False-Pass Protection**:
> Mock and cache replay executions are strictly barred from reporting `SUCCESS` or `LIVE_CONFIRMED`. They are explicitly flagged as `DEMO_NOT_FINAL` or `TEST_ONLY`.

---

## Authoritative Test Suite Verification

Run the comprehensive test discovery command:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

### Discovery Results

- **Offline Discovery**:
  - **Discovered Tests**: **88**
  - **Passed**: **87**
  - **Skipped**: **1** (`test_live_base_sepolia.py` skipped by default during offline CI)
  - **Failed**: **0**

- **Live Test Discovery (`RUN_LIVE_BLOCKCHAIN_TESTS=1`)**:
  - **Discovered Tests**: **88**
  - **Passed**: **88**
  - **Skipped**: **0**
  - **Failed**: **0**

### Breakdown by Test Suite:
1. `tests/test_blockchain_anchoring.py` (33 tests):
   - Comprehensive Base Sepolia client tests, EVM execution, state machine, and anti-false-pass checks.
2. `tests/test_end_to_end_orchestration.py` (15 tests):
   - Master pipeline stages, detection failure, search failure, non-social rejection, verification rejection, invalid evidence, anchor recovery, hash mismatch, tamper detection, anti-false-pass rules, run ID uniqueness, secrets prevention, and forensic package consistency.
3. `tests/test_ui_server.py` (14 tests):
   - Forensic workstation server, static asset delivery, PRD FR-01 consent gating, sample catalog, stage transitions, BaseScan link integrity, tamper detection, reset flow, path traversal prevention, run artifact sanitization, and credential leak prevention.
4. `tests/test_step2_acceptance.py` (14 tests):
   - Task 3 compliance gate matrices, social domain & post regex validation, and external source gating.
5. `tests/test_step2_search.py` (6 tests):
   - Query variant generation, URL canonicalization, platform classification, candidate ranking, multi-level verification (exact SHA-256 and pHash), and mock orchestrator flow.
6. `tests/test_verification_engine.py` (5 tests):
   - Biometric similarity calibration, synthetic palette transparency handling, standard JPEG preprocessing, base64 retrieval, and candidate URL validation.
7. `tests/test_live_base_sepolia.py` (1 test):
   - Live network Base Sepolia readback & verification smoke test (gated by `RUN_LIVE_BLOCKCHAIN_TESTS=1`).
