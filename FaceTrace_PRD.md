# FaceTrace — Product Requirements Document

**Hackathon:** Hacker House Goa 2026  
**Challenge:** Shortlisting Task 3 — Face Identification & Blockchain Verification  
**PRD Version:** 2.0  
**Status:** Build-ready  
**Implementation window:** September 4–7, 2026  
**Submission deadline:** September 7, 2026, 11:59 PM IST

---

# 1. Title

## FaceTrace — Verifiable Face-Match Evidence

### Tagline
**Discover. Verify. Anchor.**

### Product concept

FaceTrace is a **privacy-conscious evidence-verification pipeline** that discovers web/social-media appearances of a consenting subject's face, independently verifies the discovered candidate using a local face-recognition model, and cryptographically anchors the resulting evidence to a public blockchain.

---

# 2. Overview

FaceTrace transforms a face-search result into an auditable evidence chain.

The core pipeline is:

```text
Face Image
    ↓
Consent & Input Validation
    ↓
Face Detection
    ↓
Face Embedding
    ↓
Genuine Face/Web Search
    ↓
Candidate Discovery
    ↓
Candidate Retrieval
    ↓
Independent Face Verification
    ↓
Evidence Construction
    ↓
SHA-256 Fingerprint
    ↓
Blockchain Commitment
    ↓
Blockchain Retrieval
    ↓
Hash Recalculation
    ↓
VERIFIED / TAMPERED
```

The critical architectural rule is:

> **The search provider discovers candidates; FaceTrace independently verifies them.**

The blockchain is used to prove **evidence integrity**, not the real-world identity of a person.

---

# 3. Problem Statement

A face-search result by itself is difficult to audit.

A search engine can return:

- an incorrect match,
- a visually similar person,
- an outdated page,
- incomplete metadata,
- or a result that later changes.

A URL or screenshot also does not establish that the evidence shown today is unchanged from the evidence used to make the original decision.

FaceTrace addresses this by creating three independent layers:

### Layer 1 — Discovery

Find candidate content through a genuine external search.

### Layer 2 — Verification

Independently compare the discovered face against the input face using our own model.

### Layer 3 — Integrity

Create a deterministic evidence record, hash it, commit the hash to blockchain, and later verify the evidence against that commitment.

The result is not:

> "Blockchain proves who this person is."

The result is:

> "A genuine search discovered this candidate, our independent verification produced this score, and this exact evidence record was committed to the blockchain and can later be checked for tampering."

---

# 4. Background / Context

Hacker House Goa Task 3 requires a pipeline that takes a face scan, identifies matching web/social content, and verifies discovered data with blockchain. It specifically requires genuine search rather than a hardcoded result, and the blockchain may be public testnet, mainnet, or local/simulated provided the data can be re-verified. No website is required.

The supplied technical research exposed an important distinction:

| Capability | What it actually answers |
|---|---|
| Exact image search | Where does this image appear? |
| Visual similarity | What images look similar? |
| Face search | Where does this person's face appear? |
| Local face verification | Is this candidate face sufficiently similar to the input face? |

Google Cloud Vision Web Detection is appropriate for image/web provenance, but it is not a dedicated cross-photo face-identity service.

FaceCheck's current API is the most relevant primary feasibility target because it exposes programmatic face-search functionality.

InsightFace is used for the independent local verification layer because the project needs direct access to face embeddings rather than relying entirely on a black-box provider verdict.

Base Sepolia is the selected blockchain network for the primary implementation.

---

# 5. Goals

## G1 — Fulfill every mandatory Task 3 requirement

Demonstrate:

```text
Face detection
+
Face encoding
+
Genuine search
+
Real matching post
+
Blockchain commitment
+
Re-verification
```

## G2 — Make face verification meaningful

The face embedding must actively affect candidate acceptance.

## G3 — Make discovery genuine

The candidate must originate from a real external search request rather than a preselected result.

## G4 — Make evidence auditable

A reviewer should be able to understand:

- what was searched,
- what was discovered,
- why the candidate was accepted,
- what evidence was recorded,
- what was committed to blockchain.

## G5 — Make tampering demonstrable

A change to the evidence must change the computed hash and produce `TAMPERED`.

## G6 — Build privacy by design

Sensitive face material should be minimized and kept off-chain.

## G7 — Maximize demo reliability

The complete pipeline should be repeatedly executable on the actual demo machine before release.

## G8 — Keep scope disciplined

Only features that materially increase compliance, credibility, trust, reliability, or judge understanding should enter the release.

---

# 6. Non-Goals

FaceTrace will **not** attempt to become:

- a surveillance platform,
- a production identity-verification service,
- a general social-media crawler,
- a social-media scraping framework,
- a consumer SaaS,
- a mobile application,
- a multi-chain system,
- a custom-trained face-recognition model,
- an AI chatbot,
- a prediction platform,
- or a complex analytics platform.

Not required:

- user accounts,
- MFA,
- RBAC,
- password recovery,
- full web hosting,
- elaborate frontend,
- direct Instagram scraping,
- Google Lens browser automation.

The task explicitly states that a website is not required.

The product will not claim that:

- face similarity equals legal identity,
- blockchain proves a person's identity,
- a search provider's result is inherently correct,
- or a low-confidence candidate is definitely the target.

---

# 7. Target Users

## Primary

### Hacker House Goa judge

The judge should understand the complete pipeline from one short demonstration.

## Secondary

### Developer

Needs reproducible installation, modular components, predictable errors, logs, and tests.

### Technical auditor

Needs evidence provenance, face similarity score, blockchain transaction, deterministic verification, and privacy information.

---

# 8. User Stories

### US-01 — Submit a face

As a user, I want to provide a face image so the system can process it.

### US-02 — Obtain a face representation

As a user, I want the system to detect the face and generate an embedding.

### US-03 — Discover genuine matches

As a user, I want the system to perform an actual external face/web search and return real candidates.

### US-04 — Verify candidates independently

As a user, I want the system to independently compare discovered candidates against the original face.

### US-05 — Understand the decision

As a reviewer, I want to see the score, threshold, source, and reasoning behind acceptance.

### US-06 — Preserve evidence integrity

As an auditor, I want the evidence to have a deterministic cryptographic fingerprint.

### US-07 — Anchor evidence

As an auditor, I want the fingerprint committed to a blockchain.

### US-08 — Re-verify later

As an auditor, I want to retrieve the commitment and verify the evidence again.

### US-09 — Detect tampering

As an auditor, I want modified evidence to produce a `TAMPERED` result.

### US-10 — Protect the subject

As a user, I want sensitive face data minimized and kept off-chain.

---

# 9. User Flow

## Main flow

```text
START
  ↓
Consent confirmed
  ↓
Select image
  ↓
Validate input
  ↓
Detect face
  ↓
Generate embedding
  ↓
Search by face
  ↓
Collect candidates
  ↓
Retrieve candidate evidence
  ↓
Detect candidate face
  ↓
Generate candidate embedding
  ↓
Calculate similarity
  ↓
Rank candidates
  ↓
Accept qualifying candidate
  ↓
Build evidence record
  ↓
Canonicalize evidence
  ↓
SHA-256
  ↓
Commit hash to Base Sepolia
  ↓
Retrieve on-chain commitment
  ↓
Recompute local hash
  ↓
Compare
  ↓
VERIFIED
```

## Tamper flow

```text
Original evidence
      ↓
Hash A
      ↓
Blockchain Hash A
      ↓
Modify one field
      ↓
Hash B
      ↓
Hash A ≠ Hash B
      ↓
TAMPERED
```

## Failure flow

```text
Search
  ↓
No qualifying candidate
  ↓
INCONCLUSIVE / NO_CANDIDATES_FOUND
```

---

# 10. Functional Requirements

## FR-01 — Consent

The system shall require confirmation that the face image belongs to a consenting subject before external face-search processing.

Demo default: **one consenting team member**.

The system shall not encourage searches of arbitrary non-consenting people.

---

## FR-02 — Input validation

The system shall accept common image formats and reject corrupted, unsupported, empty, or unusable inputs.

---

## FR-03 — Face detection

The system shall detect at least one face.

Output:

```text
bounding_box
detection_confidence
face_crop/internal representation
```

No face:

`NO_FACE_DETECTED`

---

## FR-04 — Face embedding

The system shall generate a deterministic face embedding.

Primary implementation: **InsightFace / ArcFace**.

---

## FR-05 — Genuine external search

The system shall perform a real external search.

The selected provider shall not receive a preselected URL as the answer.

Primary provider: **FaceCheck.ID**.

---

## FR-06 — Search provenance

For each search request, record:

- provider,
- search method,
- request time,
- search/case identifier,
- candidate result metadata.

---

## FR-07 — Candidate discovery

The system shall normalize search results into:

```json
{
  "source_url": "...",
  "image_url": "...",
  "provider": "...",
  "provider_score": 0,
  "discovery_type": "face_search"
}
```

---

## FR-08 — Candidate retrieval

The system shall attempt to retrieve sufficient evidence for independent verification.

Possible states:

```text
RETRIEVED
UNREACHABLE
NO_USABLE_IMAGE
NO_DETECTABLE_FACE
```

---

## FR-09 — Independent face verification

Every candidate considered for acceptance shall be independently processed with the local face model.

The system shall calculate similarity between:

```text
query embedding
        ↕
candidate embedding
```

---

## FR-10 — Candidate scoring

The system shall record:

- provider score,
- face similarity,
- detection confidence,
- retrieval status,
- decision.

Thresholds shall be configuration-driven and empirically calibrated before release.

---

## FR-11 — Candidate decision

Possible decisions:

```text
ACCEPTED
REJECTED
INCONCLUSIVE
UNREACHABLE
```

Search-provider confidence alone must never generate final acceptance.

---

## FR-12 — Evidence object

The system shall create a structured evidence record.

Minimum structure:

```json
{
  "case_id": "uuid",
  "query_image_sha256": "...",
  "discovery": {
    "provider": "facecheck",
    "method": "face_search",
    "timestamp_utc": "..."
  },
  "candidate": {
    "source_url": "...",
    "platform": "...",
    "image_sha256": "...",
    "provider_score": 0,
    "face_similarity": 0,
    "threshold": 0,
    "decision": "accepted"
  },
  "model": {
    "name": "ArcFace",
    "version": "..."
  },
  "pipeline_version": "1.0.0"
}
```

---

## FR-13 — Evidence canonicalization

The evidence shall be serialized deterministically using:

- UTF-8,
- sorted object keys,
- deterministic number representation,
- deterministic timestamp representation,
- no unnecessary whitespace.

The canonical representation becomes the input to SHA-256.

---

## FR-14 — Cryptographic fingerprint

The system shall calculate:

```text
SHA-256(canonical_evidence)
```

The same evidence must always produce the same digest.

---

## FR-15 — Blockchain commitment

The system shall commit the evidence hash to Base Sepolia.

Only minimum necessary commitment information shall be stored on-chain:

```text
caseId
evidenceHash
timestamp
submitterAddress
```

Do not store the face image, face embedding, raw candidate image, or unnecessary personal information on-chain.

---

## FR-16 — Blockchain retrieval

Given a case ID or transaction reference, the system shall retrieve the original commitment.

---

## FR-17 — Integrity verification

The system shall:

```text
Retrieve evidence
      ↓
Canonicalize
      ↓
SHA-256
      ↓
Read on-chain hash
      ↓
Compare
```

---

## FR-18 — Verdicts

### VERIFIED

`local_hash == on_chain_hash`

### TAMPERED

`local_hash != on_chain_hash`

### NOT_FOUND

No corresponding blockchain commitment.

### INCONCLUSIVE

Evidence insufficient for reliable candidate acceptance.

### SEARCH_UNAVAILABLE

External search could not be performed.

### NO_CANDIDATES_FOUND

Search completed successfully but returned no qualifying result.

---

## FR-19 — Audit trail

Record major pipeline transitions:

```text
INPUT_RECEIVED
FACE_DETECTED
EMBEDDING_GENERATED
SEARCH_STARTED
CANDIDATES_FOUND
CANDIDATE_RETRIEVED
CANDIDATE_VERIFIED
EVIDENCE_CREATED
HASH_CREATED
BLOCKCHAIN_COMMITTED
VERIFICATION_COMPLETED
```

---

## FR-20 — Privacy audit

Each case shall expose a privacy status:

```text
CONSENT
DATA_MINIMIZATION
OFF_CHAIN_BIOMETRIC_DATA
NO_SENSITIVE_DATA_ON_CHAIN
SECRET_PROTECTION
TEMPORARY_DATA_CLEANUP
```

---

## FR-21 — Secure cleanup

After processing, temporary face-related artifacts should be removed according to the configured retention policy.

The cleanup operation shall be auditable without logging sensitive content.

---

## FR-22 — Tamper demonstration

The system shall support deliberate modification of one evidence field and demonstrate:

```text
Original → VERIFIED
Modified → TAMPERED
Restored → VERIFIED
```

---

## FR-23 — One-command execution

The complete primary workflow shall be executable through one command/interface action.

Conceptually:

```bash
python -m app verify --image samples/demo.jpg
```

The exact command may change during implementation.

---

## FR-24 — Evidence replay

The system should retain sufficient non-sensitive provenance to replay a case's verification logic.

Replay should show:

- case ID,
- original input fingerprint,
- search provider/method,
- candidate selected,
- similarity score,
- evidence hash,
- blockchain commitment,
- resulting verification status.

Replay must not claim that it re-ran an external search unless a new external search actually occurred.

---

# 11. Non-Functional Requirements

## NFR-01 — Reliability

The complete successful pipeline shall execute **three consecutive times** before final release.

## NFR-02 — Reproducibility

Evidence hashing must be deterministic.

## NFR-03 — Modularity

Search and blockchain providers must be replaceable.

## NFR-04 — Security

Secrets must never be hardcoded or committed.

## NFR-05 — Privacy

Biometric material must not be stored on-chain.

## NFR-06 — Auditability

Every major state transition shall be explainable.

## NFR-07 — Transparency

The product shall clearly distinguish:

```text
SEARCH RESULT
vs.
FACE VERIFICATION
vs.
BLOCKCHAIN INTEGRITY
```

## NFR-08 — Performance

The system should provide a responsive demonstration and expose stage-level timing.

## NFR-09 — Maintainability

Use modular functions/classes, structured errors, typed interfaces where practical, and configuration separation.

## NFR-10 — Demo clarity

A judge must be able to understand the result without reading the source code.

---

# 12. Edge Cases

## Input

### E1 — No face

`NO_FACE_DETECTED`

### E2 — Multiple faces

Require explicit selection or choose the highest-confidence face with an explicit notice.

### E3 — Poor-quality face

`INCONCLUSIVE`

### E4 — Corrupted image

`INVALID_INPUT`

---

## Search

### E5 — No result

`NO_CANDIDATES_FOUND`

### E6 — Provider unavailable

`SEARCH_UNAVAILABLE`

### E7 — False/irrelevant candidates

Reject through independent face verification.

### E8 — Candidate page inaccessible

`UNREACHABLE`

### E9 — Candidate image unavailable

Candidate cannot become accepted evidence.

### E10 — Candidate contains no detectable face

Reject candidate.

---

## Blockchain

### E11 — RPC failure

Retry through configured secondary provider.

### E12 — Transaction failure

Do not claim blockchain commitment.

### E13 — Case not found

`NOT_FOUND`

### E14 — Hash mismatch

`TAMPERED`

---

## Privacy/security

### E15 — API key appears in logs

Release blocked.

### E16 — Private key appears in repository

Release blocked.

### E17 — Sensitive data stored on-chain

Release blocked.

---

# 13. Acceptance Criteria

## AC-01 — Face processing

A valid single-face image produces:

```text
face detected
+
embedding generated
```

## AC-02 — Genuine search

The final demonstration must show an actual external search being performed and must not use a hardcoded candidate.

## AC-03 — Real candidate

At least one qualifying discovered result must correspond to a real web/social-media source, and its source URL must be inspectable.

## AC-04 — Independent verification

The candidate must be independently processed by the local face-recognition model with a recorded similarity score, threshold, and decision.

## AC-05 — Evidence

The system creates a deterministic evidence object.

## AC-06 — Hash

Repeated hashing of unchanged evidence produces identical SHA-256.

## AC-07 — Blockchain

The evidence hash is written to Base Sepolia and retrieved successfully.

## AC-08 — VERIFIED

Unchanged evidence produces `VERIFIED`.

## AC-09 — TAMPERED

Modified evidence produces `TAMPERED`.

## AC-10 — Honest failure

A no-result test produces `NO_CANDIDATES_FOUND` rather than fabricated success.

## AC-11 — Privacy

The final case demonstrates consent, no face image on-chain, no embedding on-chain, and appropriate temporary-data handling.

## AC-12 — Repeatability

Three consecutive successful end-to-end runs pass without manual correction.

## AC-13 — Submission readiness

The repository contains complete source, README, setup instructions, blockchain information, limitations, and demo instructions.

---

# 14. Dependencies

## Primary face-processing dependency

**InsightFace / ArcFace**

Used for local detection, embedding, and independent candidate verification.

## Primary search dependency

**FaceCheck.ID API**

Used for genuine face-based candidate discovery after feasibility testing.

## Search fallback

**Google Cloud Vision Web Detection**

Used for image/web provenance when appropriate. It must not be represented as cross-photo face-identity search.

## Blockchain

**Base Sepolia**

## Blockchain client

Python EVM tooling such as `web3.py`.

## Cryptography

Python SHA-256 tooling.

## Local development chain

Anvil/Hardhat may be used for testing and offline development.

## Configuration

Environment variables via `.env` during local development.

---

# 15. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Face-search provider returns no useful candidate | Critical | Prove feasibility immediately; maintain fallback |
| Candidate URL/image cannot be retrieved | Critical | Make retrieval its own feasibility gate |
| Search provider outage | High | Provider abstraction + fallback |
| Search result is a false positive | High | Independent local ArcFace verification |
| Similarity threshold incorrect | High | Empirical calibration |
| API quota/rate limit | Medium | Minimal calls + early testing |
| RPC failure | High | Managed RPC + secondary provider |
| macOS dependency issue | High | Prove environment early |
| Privacy problem | High | Consenting subject only |
| Secret leakage | Critical | `.env`, `.gitignore`, release security check |
| Scope explosion | Critical | P0/P1/P2 feature discipline |
| Final demo failure | Critical | Three rehearsals + backup recording |
| Model licensing uncertainty | Medium | Document applicable model terms |
| Provider interpretation mismatch | High | Clearly distinguish face search from image provenance |

---

# 16. Success Metrics

## Mandatory

### SM-01

100% of mandatory Task 3 requirements satisfied.

### SM-02

100% of final-demo candidates originate from genuine external search.

### SM-03

100% of accepted candidates are independently face-verified.

### SM-04

100% of successful cases have a valid blockchain commitment.

### SM-05

100% of unchanged evidence verifies successfully.

### SM-06

100% of controlled evidence modifications are detected as tampering.

### SM-07

Three consecutive complete successful runs before release.

### SM-08

Zero secrets committed to GitHub.

### SM-09

Zero face embeddings or raw face images stored on-chain.

---

# 17. Rollout Plan

This is a hackathon project, so rollout is a sequence of **SDLC release gates**, not a production deployment.

## Phase 1 — Requirements Freeze

### Deliverable

This PRD.

### Exit condition

No ambiguity about mandatory pipeline, privacy model, search strategy, evidence model, or blockchain model.

---

## Phase 2 — Feasibility Gate

### Highest priority

Prove:

```text
Consented image
 ↓
FaceCheck
 ↓
Real candidate
 ↓
Retrievable candidate image
 ↓
InsightFace
 ↓
Similarity score
```

### Exit condition

At least one genuine candidate can be independently verified.

### Hard rule

**No blockchain development before this passes.**

---

## Phase 3 — Core Pipeline

Build:

```text
Face
→ Search
→ Retrieval
→ Verification
```

### Exit condition

Reliable positive and negative candidate processing.

---

## Phase 4 — Evidence Layer

Build:

```text
Candidate
→ Evidence
→ Canonicalization
→ SHA-256
```

### Exit condition

Hash determinism tests pass.

---

## Phase 5 — Blockchain Layer

Build:

```text
Hash
→ Contract
→ Transaction
→ Retrieval
→ Verification
```

### Exit condition

Real testnet commitment works.

---

## Phase 6 — Trust Layer

Add:

- privacy audit,
- audit trail,
- lineage,
- explainable score,
- cleanup,
- tamper simulation,
- evidence replay.

These features strengthen the core product rather than distracting from it.

---

## Phase 7 — System Testing

Test:

- positive case,
- negative case,
- no face,
- no result,
- inaccessible candidate,
- malformed evidence,
- RPC failure,
- modified evidence,
- secret leakage.

### Exit condition

All expected states are handled honestly.

---

## Phase 8 — Release Candidate

Freeze the system.

After this point:

**Bug fixes only.**

---

## Phase 9 — Demo Release

The final recording must show:

```text
INPUT
 ↓
FACE DETECTION
 ↓
GENUINE SEARCH
 ↓
REAL RESULT
 ↓
INDEPENDENT VERIFICATION
 ↓
EVIDENCE
 ↓
HASH
 ↓
BLOCKCHAIN
 ↓
RE-VERIFICATION
 ↓
VERIFIED

then:

TAMPER
 ↓
TAMPERED
```

The final recording should be a clean, plain screen recording as required by the challenge.

---

## Phase 10 — Final Submission

Before submission:

```text
[ ] GitHub repository accessible
[ ] README complete
[ ] No secrets committed
[ ] Blockchain details correct
[ ] Transaction reference verified
[ ] Demo recording works
[ ] Search result genuinely discovered
[ ] Full pipeline rehearsed
[ ] Submission form completed
```

Submit with a meaningful buffer before the deadline.

---

# 18. Open Questions

These are implementation gates rather than reasons to delay development.

### OQ-01 — Does FaceCheck provide a qualifying result for our consenting demo subject?

**Must resolve first.**

### OQ-02 — Can the returned candidate image/evidence actually be retrieved?

**Must resolve alongside OQ-01.**

### OQ-03 — What similarity threshold performs correctly on our data?

Determine empirically using positive and negative samples.

### OQ-04 — Is a minimal smart contract worth the time versus transaction calldata?

**Default:** minimal contract.

Override only if it threatens the deadline.

### OQ-05 — What evidence should be retained off-chain?

**Default:** minimum required for demonstration and verification.

### OQ-06 — Can the fallback search path satisfy the exact organizer interpretation?

Document this explicitly. Never represent image provenance as face identity.

---

# 19. Release Notes / Change History

## Version 2.0 — September 4, 2026

### Major changes

- Reframed product as a **verifiable evidence pipeline**.
- Made **independent face verification** a mandatory capability.
- Added a dedicated **Privacy-by-Design Evidence Layer**.
- Added explicit consent gate.
- Added data classification/lifecycle controls.
- Added privacy audit.
- Defined hash-only blockchain strategy.
- Added audit trail and evidence lineage.
- Added explainable verification scores.
- Added data validation.
- Added explicit integrity/anomaly states.
- Added one-command execution.
- Added evidence replay.
- Added tamper demonstration.
- Removed irrelevant generic hackathon features from release scope.
- Locked FaceCheck as the primary search feasibility target.
- Locked InsightFace/ArcFace as the primary local verification technology.
- Locked Base Sepolia as the blockchain target.
- Formalized SDLC release gates.

### Version 1.0 → 2.0 rationale

The earlier PRD mixed product requirements with implementation details and allowed too much ambiguity around what constitutes a meaningful match.

Version 2.0 establishes:

```text
DISCOVERY
Search provider

        ↓

VERIFICATION
Our face model

        ↓

EXPLANATION
Scores + provenance

        ↓

EVIDENCE
Canonical record

        ↓

INTEGRITY
SHA-256

        ↓

ANCHOR
Blockchain

        ↓

AUDIT
Re-verification + tamper detection
```

---

# Final Product Definition

FaceTrace is complete when one observer can watch a single run and understand this chain:

**A consented face was submitted → a real search discovered a web/social candidate → our system independently verified the candidate face → the exact resulting evidence was fingerprinted → that fingerprint was committed to blockchain → the evidence was retrieved and re-hashed → the system demonstrated VERIFIED → modifying the evidence demonstrated TAMPERED.**

The product is intentionally small, auditable, and evidence-first. It avoids generic features that do not strengthen the Task 3 judging story.
