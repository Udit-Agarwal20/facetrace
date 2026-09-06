#!/usr/bin/env python3
"""
FaceTrace — Feasibility Gate Runner
Validates:
Consented Image -> InsightFace Detection -> Genuine FaceCheck Search ->
Real Candidate -> Candidate Retrieval -> Independent Verification -> Similarity Score.
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Ensure root workspace is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

# Load .env variables
load_dotenv(WORKSPACE_ROOT / ".env")

from src.core.face_engine import FaceEngine
from src.providers.facecheck_provider import FaceCheckProvider
from src.core.candidate_retriever import CandidateRetriever
from src.core.verifier import FaceVerifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("FaceTrace.Feasibility")


def print_banner():
    banner = """
================================================================================
                    FACETRACE — FEASIBILITY GATE RUNNER
           Privacy-Conscious Verifiable Face-Match Evidence Pipeline
================================================================================
"""
    print(banner)


def run_feasibility_gate(
    image_path: Path,
    consent_confirmed: bool,
    api_token: Optional[str] = None,
    demo_mode: bool = True,
    threshold: float = 0.72,
    model_name: str = "buffalo_sc"
) -> bool:
    print_banner()

    # --------------------------------------------------------------------------
    # GATE 0: CONSENT VERIFICATION (PRD FR-01)
    # --------------------------------------------------------------------------
    print("[PHASE 0] CONSENT & INPUT VALIDATION")
    if not consent_confirmed:
        print("[-] REJECTED: Subject consent has not been confirmed.")
        print("    Requirement FR-01 specifies that face search must only occur")
        print("    with documented subject consent.")
        print("    Run with --consent to confirm consent for this evaluation.")
        return False

    if not image_path.exists():
        print(f"[-] ERROR: Input image does not exist at: {image_path}")
        return False

    print(f"[+] Subject consent verified.")
    print(f"[+] Input image target: {image_path} ({image_path.stat().st_size / 1024:.1f} KB)")
    print()

    # --------------------------------------------------------------------------
    # GATE 1: LOCAL FACE DETECTION & EMBEDDING (InsightFace / ArcFace)
    # --------------------------------------------------------------------------
    print(f"[PHASE 1] LOCAL FACE DETECTION & EMBEDDING (Model: {model_name})")
    face_engine = FaceEngine(model_name=model_name)

    # Preprocessing inspection & logging (as required by diagnostics)
    from PIL import Image
    with Image.open(image_path) as raw_pil:
        raw_mode = raw_pil.mode
        raw_size = raw_pil.size
        has_trans = ("transparency" in raw_pil.info) or (raw_mode in ("RGBA", "LA", "P"))

    bgr_data = face_engine.load_image_bgr(image_path)
    h, w, c = bgr_data.shape
    print(f"[+] Image Preprocessing Details:")
    print(f"    - Raw Mode:           {raw_mode} (transparency={has_trans})")
    print(f"    - Converted Format:   OpenCV BGR (safe composited)")
    print(f"    - Dimensions:         {w}x{h} (width x height)")
    print(f"    - Channels:           {c}")
    print(f"    - Array Dtype:        {bgr_data.dtype}")
    print(f"    - Pixel Value Range:  [{int(bgr_data.min())}, {int(bgr_data.max())}] (mean: {float(bgr_data.mean()):.1f})")

    query_result = face_engine.detect_and_embed(bgr_data)

    if not query_result.detected:
        print(f"[-] ERROR: Face detection failed: {query_result.error}")
        return False

    print(f"[+] Face detected successfully!")
    print(f"    - Bounding Box:       {query_result.bbox}")
    print(f"    - Detection Score:    {query_result.detection_score:.4f}")
    print(f"    - Embedding Vector:   512-dim ArcFace (unit-normalized)")
    print(f"    - Faces in Image:     {query_result.num_faces}")
    print()

    # --------------------------------------------------------------------------
    # GATE 2: GENUINE EXTERNAL FACE SEARCH (FaceCheck.ID REST API)
    # --------------------------------------------------------------------------
    print(f"[PHASE 2] GENUINE EXTERNAL FACE SEARCH (FaceCheck.ID)")
    resolved_token = api_token or os.getenv("FACECHECK_API_TOKEN", "").strip()

    if not resolved_token:
        print("[-] BLOCKED: No FaceCheck API Token provided.")
        print("    Please set FACECHECK_API_TOKEN in your .env file or pass via --api-token.")
        print("    Get your API token at: https://facecheck.id/Face-Search/API")
        return False

    provider = FaceCheckProvider(api_token=resolved_token, demo_mode=demo_mode)
    info = provider.get_info()
    if info.get("raw", {}).get("error"):
        print(f"[-] API Token Validation Failed: {info['raw']['error']} (Code: {info['raw'].get('code')})")
        print("    Please verify your token in .env or at https://facecheck.id/Face-Search/API")
        return False

    credits = info.get("credits", 0)
    print(f"[+] FaceCheck account validated (Credits available: {credits})")

    mode_label = "DEMO (100k faces, 0 credits)" if demo_mode else "LIVE (Full web index, 3 credits)"
    print(f"[+] Dispatching genuine search request (Mode: {mode_label})...")

    upload_res = provider.upload_image(image_path)
    if not upload_res.get("success"):
        print(f"[-] Search Upload Failed: {upload_res.get('error')} (Code: {upload_res.get('code')})")
        return False

    id_search = upload_res["id_search"]
    print(f"[+] Image uploaded. Search session active: id_search={id_search}")
    print("[+] Polling search execution...")

    search_result = provider.poll_search(id_search=id_search, max_wait_seconds=180, poll_interval=2.5)

    if not search_result.success:
        print(f"[-] Search Execution Failed: {search_result.error} (Code: {search_result.error_code})")
        return False

    candidates = search_result.candidates
    print(f"[+] Search Completed. Discovered Candidates: {len(candidates)}")
    print()

    if not candidates:
        print("[!] NO_CANDIDATES_FOUND: Search finished honestly with 0 qualifying candidates.")
        print("    This satisfies AC-10 (Honest failure), but does not complete the positive verification gate.")
        return False

    # --------------------------------------------------------------------------
    # GATE 3: CANDIDATE DISCOVERY & VALIDATION
    # --------------------------------------------------------------------------
    print("[PHASE 3] DISCOVERED CANDIDATES (Top matches)")
    print(f"{'Idx':<4} {'Candidate ID':<18} {'Provider Score':<16} {'Source URL'}")
    print("-" * 80)
    for idx, cand in enumerate(candidates[:5]):
        short_url = (cand.source_url[:45] + "...") if len(cand.source_url) > 48 else cand.source_url
        ext_tag = "" if cand.is_external_source() else " [INTERNAL PLACEHOLDER]"
        print(f"{idx+1:<4} {cand.candidate_id:<18} {cand.provider_score:<16} {short_url}{ext_tag}")
    print("-" * 80)
    print()

    # Validation Rule: Demo Mode Enforcement
    if demo_mode:
        print("[!] VALIDATION RULE ENFORCEMENT:")
        print("    - Search was executed in DEMO/TEST mode (demo=True).")
        print("    - FaceCheck documentation notes demo searches scan synthetic/limited data.")
        print("    - Discovered candidate URLs point to internal placeholders (facecheck.id).")
        print("    - Per product rule: Demo results CANNOT satisfy FEASIBILITY_PASS.")
        print()

    # --------------------------------------------------------------------------
    # GATE 4: CANDIDATE RETRIEVAL & INDEPENDENT VERIFICATION
    # --------------------------------------------------------------------------
    print("[PHASE 4] INDEPENDENT CANDIDATE VERIFICATION (InsightFace ArcFace)")
    retriever = CandidateRetriever()
    verifier = FaceVerifier(threshold=threshold)

    qualifying_candidate = None
    qualifying_retrieval = None
    qualifying_face_result = None
    qualifying_decision = None

    for idx, cand in enumerate(candidates):
        # Validation Rule: Candidate source URL must be genuine external page
        if not demo_mode and not cand.is_external_source():
            logger.info(f"Skipping candidate {cand.candidate_id}: internal facecheck.id placeholder.")
            continue

        retrieval_res = retriever.retrieve_candidate(cand)
        if retrieval_res.status != "RETRIEVED" or retrieval_res.pil_image is None:
            continue

        cand_face_res = face_engine.detect_and_embed(retrieval_res.pil_image)
        if not cand_face_res.detected or cand_face_res.embedding is None:
            continue

        decision = verifier.evaluate(
            query_embedding=query_result.embedding,
            candidate_embedding=cand_face_res.embedding,
            candidate_id=cand.candidate_id,
            source_url=cand.source_url,
            candidate_detection_score=cand_face_res.detection_score,
            provider_score=cand.provider_score
        )

        qualifying_candidate = cand
        qualifying_retrieval = retrieval_res
        qualifying_face_result = cand_face_res
        qualifying_decision = decision
        break

    if qualifying_candidate:
        print(f"[+] Qualifying Candidate Found: {qualifying_candidate.candidate_id}")
        print(f"    Source URL:          {qualifying_candidate.source_url}")
        print(f"    External Validated:  {qualifying_candidate.is_external_source()}")
        print(f"    Candidate Retrieval: {qualifying_retrieval.status} ({qualifying_retrieval.content_type})")
        print(f"    Face Detection:      Score {qualifying_face_result.detection_score:.4f}")
        print(f"    Local Similarity:    {qualifying_decision.similarity:.4f} (Threshold: {threshold:.2f})")
        print(f"    Local Decision:      {qualifying_decision.decision}")
    else:
        print("[-] No qualifying candidate with retrievable face could be verified.")
        if demo_mode:
            print("    (Expected in DEMO mode: placeholder thumbnails do not correspond to target face).")

    # --------------------------------------------------------------------------
    # GATE 5: GATE EVALUATION & SDLC STATUS
    # --------------------------------------------------------------------------
    print()
    print("=" * 80)
    print("                         GATE EVALUATION AUDIT")
    print("=" * 80)
    print(f"1. Subject Consent Verified:         PASS (FR-01)")
    print(f"2. Local Face Detection & Embedding: PASS ({query_result.num_faces} face, {query_result.detection_score:.4f} conf, 512-d ArcFace)")
    print(f"3. External Search Executed:         PASS (FaceCheck session id_search={id_search})")
    print(f"4. Search Mode:                      {'LIVE (3 credits)' if not demo_mode else 'DEMO (synthetic/unbilled)'}")
    print(f"5. External Source URL Verified:     {'PASS' if qualifying_candidate and qualifying_candidate.is_external_source() else 'FAIL / DEMO_PLACEHOLDER'}")
    print(f"6. Candidate Evidence Retrievable:   {'PASS' if qualifying_retrieval and qualifying_retrieval.status == 'RETRIEVED' else 'FAIL'}")
    print(f"7. Candidate Face Detectable:        {'PASS' if qualifying_face_result and qualifying_face_result.detected else 'FAIL'}")
    print(f"8. Independent ArcFace Similarity:   {'PASS (' + str(qualifying_decision.similarity) + ')' if qualifying_decision else 'FAIL'}")
    print("=" * 80)

    if not demo_mode and qualifying_candidate and qualifying_candidate.is_external_source() and qualifying_decision:
        print("[STATUS] >>> FEASIBILITY_PASS <<<")
        print("All five criteria satisfied in LIVE mode with genuine external web candidate.")
        print("=" * 80)
        return "FEASIBILITY_PASS"

    if demo_mode and len(candidates) > 0:
        print("[STATUS] >>> API_INTEGRATION_PASS (FEASIBILITY GATE: PARTIAL) <<<")
        print("FaceCheck REST API upload, authentication, and progress polling succeeded.")
        print("However, DEMO mode does not produce valid external social/web evidence.")
        print("Run with --live on a consented subject image to advance to FEASIBILITY_PASS.")
        print("=" * 80)
        return "API_INTEGRATION_PASS"

    print("[STATUS] >>> FEASIBILITY_FAIL <<<")
    print("Core feasibility pipeline requirements were not satisfied.")
    print("=" * 80)
    return "FEASIBILITY_FAIL"


def main():
    parser = argparse.ArgumentParser(description="FaceTrace Feasibility Gate Runner")
    parser.add_argument("--image", type=str, default=None, help="Path to input face image")
    parser.add_argument("--consent", action="store_true", help="Confirm subject consent per FR-01")
    parser.add_argument("--api-token", type=str, default=None, help="FaceCheck API Token (or via .env)")
    parser.add_argument("--live", action="store_true", help="Run in live mode (deducts 3 credits).")
    parser.add_argument("--demo", action="store_true", help="Force demo mode (synthetic unbilled search).")
    parser.add_argument("--threshold", type=float, default=0.72, help="Local similarity threshold (default: 0.72)")
    parser.add_argument("--model", type=str, default="buffalo_sc", help="InsightFace model bundle (default: buffalo_sc)")
    parser.add_argument("--check-token", action="store_true", help="Verify FaceCheck API token and display remaining credits")

    args = parser.parse_args()

    resolved_token = args.api_token or os.getenv("FACECHECK_API_TOKEN", "").strip()

    if args.check_token:
        print_banner()
        print("[CHECK TOKEN] Checking FaceCheck.ID account status...")
        if not resolved_token:
            print("[-] No token found. Set FACECHECK_API_TOKEN in .env or pass --api-token.")
            sys.exit(1)
        provider = FaceCheckProvider(api_token=resolved_token)
        info = provider.get_info()
        if info.get("raw", {}).get("error"):
            print(f"[-] Token invalid: {info['raw']['error']}")
            sys.exit(1)
        print(f"[+] Token valid! Credits: {info.get('credits', 0)}, Online: {info.get('online')}, Indexed faces: {info.get('face_count'):,}")
        sys.exit(0)

    if not args.image:
        print("[-] Error: --image <path> is required when running verification.")
        parser.print_help()
        sys.exit(1)

    # Determine demo mode: --live overrides, --demo overrides, otherwise check .env
    if args.live:
        demo_mode = False
    elif args.demo:
        demo_mode = True
    else:
        demo_mode = os.getenv("FACECHECK_DEMO_MODE", "true").lower() == "true"

    image_path = Path(args.image).resolve()

    gate_status = run_feasibility_gate(
        image_path=image_path,
        consent_confirmed=args.consent,
        api_token=args.api_token,
        demo_mode=demo_mode,
        threshold=args.threshold,
        model_name=args.model
    )

    if gate_status == "FEASIBILITY_PASS":
        sys.exit(0)
    elif gate_status == "API_INTEGRATION_PASS":
        # Successful API connectivity but partial feasibility gate
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
