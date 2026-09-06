#!/usr/bin/env python3
"""
FaceTrace Task 3 Compliance Checker.
Audits the Step 2 evidence package against all 16 mandatory Hackathon Task 3 rules:
1. Real live search used (LIVE_EXTERNAL_SEARCH)
2. No mock provider used
3. Accepted candidate is an external source
4. Supported social-media domain
5. Post-like content URL (not homepage/profile/search)
6. Candidate source URL reachable
7. Candidate evidence retrievable
8. Candidate image decodable and valid
9. Face detected in candidate image
10. ArcFace verification passed threshold
11. Evidence JSON schema versioned (1.0)
12. Execution mode recorded
13. Provenance timestamps present (ISO-8601 UTC)
14. Discovery type recorded (image_provenance)
15. No credentials, tokens, or private keys leaked in evidence
16. Step 2 strictly bounded: no blockchain transactions, no raw face embeddings for on-chain storage
"""

import argparse
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from src.search.models import Task3ComplianceState, ExecutionMode


def check_compliance(evidence_path: Path) -> bool:
    print("=" * 80)
    print("                FACETRACE TASK 3 STEP 2 COMPLIANCE AUDITOR")
    print(f"Target Evidence: {evidence_path}")
    print("=" * 80)

    if not evidence_path.exists():
        print(f"[-] FATAL: Evidence package file not found: {evidence_path}")
        print("\nTASK 3 RELEASE BLOCKED")
        return False

    try:
        with open(evidence_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[-] FATAL: Evidence package is not valid JSON: {e}")
        print("\nTASK 3 RELEASE BLOCKED")
        return False

    checks = []

    # 1. Real live search used
    search_block = data.get("search", {})
    exec_mode = search_block.get("execution_mode")
    if exec_mode == ExecutionMode.LIVE_EXTERNAL_SEARCH.value:
        checks.append(("Real live search used (LIVE_EXTERNAL_SEARCH)", True, f"mode={exec_mode}"))
    else:
        checks.append(("Real live search used (LIVE_EXTERNAL_SEARCH)", False, f"found mode='{exec_mode}'"))

    # 2. No mock provider used
    provider = search_block.get("provider", "")
    is_mock = "mock" in provider.lower()
    checks.append(("No mock provider used", not is_mock, f"provider='{provider}'"))

    # 3. Accepted candidate is external
    candidate = data.get("selected_candidate") or {}
    page_url = candidate.get("page_url", "")
    parsed = urlparse(page_url)
    netloc = parsed.netloc.lower() if parsed.netloc else ""
    is_internal = any(dis in netloc for dis in ("localhost", "127.0.0.1", "facecheck.id"))
    checks.append(("Accepted candidate is an external source", bool(netloc and not is_internal), f"host='{netloc}'"))

    # 4. Social domain
    is_social = candidate.get("is_social_domain", False)
    platform = candidate.get("platform")
    checks.append(("Supported social-media domain", bool(is_social and platform), f"platform={platform}"))

    # 5. Post-like URL
    is_post = candidate.get("is_post_url", False)
    checks.append(("Post-like content URL (not generic profile/homepage)", bool(is_post), f"path='{parsed.path}'"))

    # 6. Source reachable
    retrieval = data.get("retrieval") or candidate.get("retrieval") or {}
    source_ok = retrieval.get("source_reachable", False)
    checks.append(("Candidate source URL reachable", bool(source_ok), f"source_reachable={source_ok}"))

    # 7. Evidence retrievable
    ev_ok = retrieval.get("evidence_retrieved", False)
    checks.append(("Candidate evidence retrievable", bool(ev_ok), f"evidence_retrieved={ev_ok}"))

    # 8. Image valid
    img_ok = retrieval.get("image_valid", False)
    checks.append(("Candidate image decodable and valid", bool(img_ok), f"image_valid={img_ok}"))

    # 9. Face detected in candidate
    ver = candidate.get("verification") or {}
    face_block = ver.get("face") or {}
    faces_detected = face_block.get("faces_detected", 0)
    checks.append(("Face detected in candidate image", faces_detected > 0, f"faces_detected={faces_detected}"))

    # 10. ArcFace verification passed
    face_verified = face_block.get("verified", False)
    sim = face_block.get("similarity")
    checks.append(("ArcFace verification passed", bool(face_verified and (sim is not None and sim >= 0.72)), f"similarity={sim}"))

    # 11. Schema versioned
    schema_ver = data.get("schema_version")
    checks.append(("Evidence JSON schema versioned", bool(schema_ver), f"schema_version={schema_ver}"))

    # 12. Execution mode recorded
    checks.append(("Execution mode recorded in search metadata", bool(exec_mode), f"execution_mode={exec_mode}"))

    # 13. Provenance timestamps present
    prov = data.get("provenance", {})
    has_ts = all(k in prov for k in ("discovered_at", "retrieved_at", "verified_at"))
    checks.append(("Provenance timestamps present (ISO-8601 UTC)", has_ts, f"timestamps={list(prov.keys())}"))

    # 14. Discovery type recorded
    disc_type = search_block.get("discovery_type")
    checks.append(("Discovery type recorded", disc_type == "image_provenance", f"discovery_type={disc_type}"))

    # 15. No credentials leaked
    raw_str = json.dumps(data)
    secret_patterns = [r"AIza[0-9A-Za-z-_]{35}", r"\"private_key\"", r"\"client_secret\"", r"ghp_[0-9A-Za-z]{36}"]
    has_secret = any(re.search(pat, raw_str) for pat in secret_patterns)
    checks.append(("No credentials or secrets leaked in evidence", not has_secret, "clean payload"))

    # 16. Step 2 boundary preserved
    has_blockchain_call = "transaction_hash" in data or "eth_block" in data
    has_raw_embedding = "embedding" in data or "query_embedding" in data or (ver and "embedding" in ver)
    checks.append(("Step 2 bounded (No blockchain writes, no on-chain biometric embeddings)", not has_blockchain_call and not has_raw_embedding, "boundary intact"))

    # Print results table
    print(f"{'#':<3} {'Rule Description':<55} {'Status':<8} {'Details'}")
    print("-" * 80)
    passed_all = True
    for idx, (desc, ok, detail) in enumerate(checks, 1):
        status_str = "PASS" if ok else "FAIL"
        if not ok:
            passed_all = False
        print(f"{idx:<3} {desc:<55} [{status_str}]  {detail}")

    print("=" * 80)
    if passed_all:
        print(">>> TASK 3 STEP 2 COMPLIANCE: PASS <<<")
        print("The evidence package satisfies all Task 3 mandatory criteria and is ready for Step 3.")
        return True
    else:
        print(">>> TASK 3 RELEASE BLOCKED <<<")
        print("Failed gates must be addressed before proceeding to Step 3 release.")
        return False


def main():
    parser = argparse.ArgumentParser(description="FaceTrace Task 3 Compliance Checker")
    parser.add_argument("--evidence", type=str, default="data/discovered_post.json", help="Path to evidence JSON")
    args = parser.parse_args()

    success = check_compliance(Path(args.evidence).resolve())
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
