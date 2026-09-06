#!/usr/bin/env python3
"""
FaceTrace — Step 2 Reverse Image Search and Verification Runner.
Connects Step 1 FaceEngine output -> Step 2 SearchOrchestrator -> Discovered Post Evidence.
"""

import argparse
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import sys
from typing import Optional
from dotenv import load_dotenv

# Ensure root workspace is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

load_dotenv(WORKSPACE_ROOT / ".env")

from src.core.face_engine import FaceEngine
from src.search.models import SearchRequest, FaceInfo, FaceBoundingBox
from src.search.orchestrator import SearchOrchestrator
from src.search.providers.google_vision import GoogleVisionProvider
from src.search.providers.mock_provider import MockSearchProvider
from src.search.cache import SearchCache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("FaceTrace.Step2Runner")


def print_banner():
    banner = """
================================================================================
              FACETRACE — STEP 2 REVERSE IMAGE SEARCH WORKSPACE
              Reverse Web/Social Image Retrieval & Multi-Level Verification
================================================================================
"""
    print(banner)


def run_step2(
    image_path: Path,
    job_id: str,
    consent: bool,
    use_mock: bool = False,
    no_cache: bool = False,
    live: bool = False,
    compliance: bool = False,
    output_path: Optional[Path] = None
) -> bool:
    print_banner()

    # --------------------------------------------------------------------------
    # 0. Consent & Input Validation (PRD FR-01)
    # --------------------------------------------------------------------------
    if not consent:
        print("[-] REJECTED: Subject consent has not been confirmed.")
        print("    Requirement FR-01 specifies that face search must only occur")
        print("    with documented subject consent.")
        print("    Run with --consent to confirm consent for this evaluation.")
        return False

    if not image_path.exists():
        print(f"[-] ERROR: Input image not found: {image_path}")
        return False

    print(f"[JOB ID]         {job_id}")
    print(f"[INPUT IMAGE]    {image_path} ({image_path.stat().st_size / 1024:.1f} KB)")
    print(f"[CONSENT]        VERIFIED")
    print(f"[EXECUTION MODE] {'MOCK' if use_mock else ('LIVE EXTERNAL' if (live or compliance) else 'STANDARD')}")
    print(f"[COMPLIANCE]     {'ENFORCED (Hard Social-Post Gate)' if compliance else 'STANDARD'}")
    print()

    # --------------------------------------------------------------------------
    # 1. Step 1: Face Detection & Embedding (InsightFace ArcFace)
    # --------------------------------------------------------------------------
    print("[STEP 1] LOCAL FACE DETECTION & EMBEDDING (InsightFace ArcFace)")
    face_engine = FaceEngine(model_name=os.getenv("INSIGHTFACE_MODEL_NAME", "buffalo_sc"))
    det_result = face_engine.detect_and_embed(image_path)

    if not det_result.detected:
        print(f"[-] ERROR: Face detection failed in Step 1: {det_result.error}")
        return False

    bbox = FaceBoundingBox.from_list(det_result.bbox)
    print(f"[+] Face detected successfully:")
    print(f"    - BBox (x, y, w, h): [{bbox.x:.1f}, {bbox.y:.1f}, {bbox.width:.1f}, {bbox.height:.1f}]")
    print(f"    - Detection Score:   {det_result.detection_score:.4f}")
    print(f"    - Embedding:         512-dim ArcFace vector (unit-normalized)")
    print()

    # Assemble Step 1 output contract for Step 2
    face_info = FaceInfo(
        bbox=bbox,
        aligned_face=None,
        embedding=det_result.embedding,
        detection_score=det_result.detection_score
    )

    search_request = SearchRequest(
        job_id=job_id,
        original_image=str(image_path),
        face=face_info
    )

    # --------------------------------------------------------------------------
    # 2. Step 2: Search Orchestrator Setup
    # --------------------------------------------------------------------------
    provider_name = "Mock Provider (Offline)" if use_mock else "Google Cloud Vision Web Detection"
    print(f"[STEP 2] REVERSE IMAGE RETRIEVAL & VERIFICATION")
    print(f"[+] Active Provider: {provider_name}")

    if use_mock:
        provider = MockSearchProvider()
    else:
        provider = GoogleVisionProvider()

    require_live_search = live or compliance or no_cache
    cache = SearchCache(enabled=not no_cache)
    orchestrator = SearchOrchestrator(
        provider=provider,
        cache=cache
    )

    # Execute Step 2
    out_file = output_path or Path("data/discovered_post.json")
    result = orchestrator.search(search_request, output_path=out_file, require_live=require_live_search)

    # --------------------------------------------------------------------------
    # 3. Observability & Forensic Summary
    # --------------------------------------------------------------------------
    print()
    print("=" * 80)
    print("                        STEP 2 SEARCH AUDIT TRAIL")
    print("=" * 80)
    print(f"Status:                      {result.status}")
    print(f"Provider:                    {result.search.get('provider')}")
    print(f"Discovery Type:              {result.search.get('discovery_type')}")
    print(f"Execution Mode:              {result.search.get('execution_mode')}")
    print(f"Queries Executed:            {result.search.get('queries_executed')}")
    print(f"Raw Candidates Discovered:   {result.metrics.get('raw_candidate_count')}")
    print(f"Deduplicated Candidates:     {result.metrics.get('deduplicated_count')}")
    print(f"Social Platform Candidates:  {result.metrics.get('social_candidate_count')}")
    print(f"Post-like URLs:              {result.metrics.get('post_url_count')}")
    print(f"Total Verified Candidates:   {result.metrics.get('verified_candidate_count')}")
    print(f"  - Qualifying Social Posts: {result.metrics.get('qualifying_social_post_count', 0)}")
    print(f"  - Web Matches Only:        {result.metrics.get('web_matches_only_count', 0)}")
    print(f"Total Execution Time:        {result.metrics.get('total_latency_ms')} ms")
    print("-" * 80)

    # Task 3 Compliance Breakdown
    comp = result.task3_compliance or {}
    print("TASK 3 COMPLIANCE GATE EVALUATION:")
    print(f"  Compliance State:          {comp.get('state')}")
    print(f"  Task 3 Gate Passed:        {comp.get('passed')}")
    if comp.get("failed_gates"):
        print("  Failed Conditions:")
        for gate in comp.get("failed_gates", []):
            print(f"    ✗ {gate}")
    print(f"  Compliance Explanation:    {comp.get('reason')}")
    print("-" * 80)

    sel = result.selected_candidate
    if sel:
        print("SELECTED EVIDENCE RECORD:")
        print(f"  Platform:                  {sel.get('platform') or 'Generic Web'}")
        print(f"  Page URL:                  {sel.get('page_url')}")
        print(f"  Image URL:                 {sel.get('image_url')}")
        print(f"  Provider Match Type:       {sel.get('provider_match_type')}")
        print(f"  Discovered via Queries:    {sel.get('query_variants')}")
        print(f"  Retrieval Score:           {sel.get('retrieval_score')}")

        ret = sel.get("retrieval") or {}
        print("  RETRIEVAL METRICS:")
        print(f"    - Source Reachable:      {ret.get('source_reachable')}")
        print(f"    - Evidence Retrieved:    {ret.get('evidence_retrieved')}")
        print(f"    - Image Valid:           {ret.get('image_valid')}")

        ver = sel.get("verification") or {}
        print("  INDEPENDENT VERIFICATION LADDER:")
        print(f"    - Verification State:    {ver.get('verification_state') or ver.get('classification')}")
        print(f"    - SHA-256 Byte Match:    {ver.get('sha256_exact')}")
        print(f"    - pHash Distance:        {ver.get('phash_distance')} (perceptual similarity)")
        print(f"    - Face Verified:         {ver.get('face_verified')} (similarity: {ver.get('face_similarity')}, {ver.get('faces_detected')} face(s))")
        print(f"    - Audit Explanation:     {ver.get('explanation')}")
    else:
        print("NO QUALIFYING VERIFIED POST FOUND.")

    print("=" * 80)
    print(f"[+] Output package written to: {out_file}")
    print()

    if compliance:
        # In compliance mode, requires genuine TASK 3 match
        return bool(comp.get("passed", False))
    return result.status in ("SOCIAL_POST_MATCH_FOUND", "MATCH_FOUND", "WEB_MATCH_FOUND")


def main():
    parser = argparse.ArgumentParser(description="FaceTrace Step 2 Reverse Image Search Runner")
    parser.add_argument("--image", type=str, required=True, help="Path to input face image")
    parser.add_argument("--job-id", type=str, default=None, help="Job/Scan Identifier")
    parser.add_argument("--consent", action="store_true", help="Confirm subject consent per FR-01")
    parser.add_argument("--mock", action="store_true", help="Use offline MockSearchProvider for testing without GCP billing")
    parser.add_argument("--no-cache", action="store_true", help="Disable local SHA-256 query cache")
    parser.add_argument("--live", action="store_true", help="Enforce fresh LIVE external search (bypasses cache)")
    parser.add_argument("--compliance", action="store_true", help="Enforce Task 3 Compliance Mode (fails if not genuine social post)")
    parser.add_argument("--output", type=str, default="data/discovered_post.json", help="Path to output JSON")

    args = parser.parse_args()

    job_id = args.job_id or f"scan_{int(datetime.now(timezone.utc).timestamp())}"
    image_path = Path(args.image).resolve()
    output_path = Path(args.output).resolve()

    success = run_step2(
        image_path=image_path,
        job_id=job_id,
        consent=args.consent,
        use_mock=args.mock,
        no_cache=args.no_cache,
        live=args.live,
        compliance=args.compliance,
        output_path=output_path
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
