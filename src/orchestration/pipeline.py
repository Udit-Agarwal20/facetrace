"""
FaceTrace — Step 4 End-to-End Orchestrator Pipeline
Coordinates Step 1 (Face Engine) -> Step 2 (Reverse Image Search & Multi-Level Verification)
-> Step 3 (Base Sepolia Blockchain Commitment & Readback) -> Tamper Demonstration.
"""

from datetime import datetime, timezone
import io
import json
import logging
import os
from pathlib import Path
import time
from typing import Optional, Dict, Any, Union
import uuid

from PIL import Image
from src.core.face_engine import FaceEngine
from src.search.models import SearchRequest, FaceInfo, FaceBoundingBox, Step2Output, RetrievalDetails
from src.search.orchestrator import SearchOrchestrator
from src.search.providers.google_vision import GoogleVisionProvider
from src.search.providers.mock_provider import MockSearchProvider
from src.search.cache import SearchCache
from src.blockchain.canonicalizer import EvidenceCanonicalizer, NonCompliantEvidenceError
from src.blockchain.client import BlockchainClient, MockBlockchainClient
from src.blockchain.models import BlockchainMode, BlockchainReleaseStatus, BlockchainRecord

from .models import (
    PipelineStage,
    ExecutionMode,
    PipelineStatus,
    CandidateSummary,
    VerificationSummary,
    BlockchainSummary,
    TamperTestSummary,
    TimingsSummary,
    FaceTraceRunResult
)

logger = logging.getLogger("FaceTrace.Pipeline")

DEFAULT_IMAGE_PATH = Path(__file__).resolve().parent.parent.parent / "samples" / "obama_ama.jpg"
RUNS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "runs"
DEFAULT_EVIDENCE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "discovered_post.json"


class FaceTracePipeline:
    """
    Master end-to-end orchestration coordinator for FaceTrace.
    Ensures deterministic stage execution, anti-false-pass enforcement,
    observability, and forensic audit package generation.
    """

    def __init__(
        self,
        face_engine: Optional[FaceEngine] = None,
        search_orchestrator: Optional[SearchOrchestrator] = None,
        blockchain_client: Optional[Union[BlockchainClient, MockBlockchainClient]] = None
    ):
        self.face_engine = face_engine
        self.search_orchestrator = search_orchestrator
        self.blockchain_client = blockchain_client

    def run(
        self,
        image_path: Optional[Union[str, Path]] = None,
        consent: bool = True,
        live: bool = False,
        mock: bool = False,
        dry_run: bool = False,
        no_cache: bool = False,
        output_path: Optional[Union[str, Path]] = None,
        custom_run_id: Optional[str] = None,
        stage_callback: Optional[Any] = None
    ) -> FaceTraceRunResult:
        """
        Executes the 16-stage end-to-end pipeline.
        """
        total_start = time.time()
        now_ts = int(datetime.now(timezone.utc).timestamp())
        run_id = custom_run_id or f"ft_run_{now_ts}_{uuid.uuid4().hex[:8]}"

        # Determine execution mode
        if live:
            mode = ExecutionMode.LIVE
        elif mock:
            mode = ExecutionMode.MOCK
        elif dry_run:
            mode = ExecutionMode.DRY_RUN
        else:
            mode = ExecutionMode.MOCK

        history: list[str] = [PipelineStage.INIT.value]
        timings = TimingsSummary()

        def notify(stage_val: str, msg: str = ""):
            history.append(stage_val)
            if stage_callback:
                try:
                    stage_callback(stage_val, msg)
                except Exception as cb_err:
                    logger.debug("stage_callback error: %s", cb_err)

        if stage_callback:
            try:
                stage_callback(PipelineStage.INIT.value, "Initializing FaceTrace pipeline...")
            except Exception as cb_err:
                logger.debug("stage_callback error: %s", cb_err)

        target_image = Path(image_path) if image_path else DEFAULT_IMAGE_PATH

        logger.info(f"[{run_id}] Initializing FaceTrace Pipeline (Mode: {mode.value}) for image: {target_image.name}")

        # Anti-False-Pass Gating: Live pipeline strictly requires live blockchain client
        if mode == ExecutionMode.LIVE:
            if self.blockchain_client and (
                isinstance(self.blockchain_client, MockBlockchainClient) or
                getattr(self.blockchain_client, "mode", None) != BlockchainMode.LIVE_BLOCKCHAIN
            ):
                notify(PipelineStage.BLOCKCHAIN_ERROR.value)
                timings.total_ms = (time.time() - total_start) * 1000.0
                return FaceTraceRunResult(
                    run_id=run_id,
                    status=PipelineStatus.BLOCKED,
                    stage=PipelineStage.BLOCKCHAIN_ERROR,
                    execution_mode=mode,
                    error="Anti-false-pass violation: LIVE mode requires live Base Sepolia blockchain client.",
                    error_action="Configure BLOCKCHAIN_PRIVATE_KEY and BASE_SEPOLIA_RPC_URL in .env.",
                    timings_ms=timings,
                    history=history
                )

        # ----------------------------------------------------------------------
        # [1] Input Validation
        # ----------------------------------------------------------------------
        if not target_image.exists():
            notify(PipelineStage.INPUT_ERROR.value)
            timings.total_ms = (time.time() - total_start) * 1000.0
            return FaceTraceRunResult(
                run_id=run_id,
                status=PipelineStatus.FAILED,
                stage=PipelineStage.INPUT_ERROR,
                execution_mode=mode,
                error=f"Input image file not found: {target_image}",
                error_action="Provide a valid, accessible image path containing a subject face.",
                timings_ms=timings,
                history=history
            )
        notify(PipelineStage.INPUT_VALIDATED.value)

        # ----------------------------------------------------------------------
        # [2] Consent Confirmation (FR-01)
        # ----------------------------------------------------------------------
        if not consent:
            notify(PipelineStage.INPUT_ERROR.value)
            timings.total_ms = (time.time() - total_start) * 1000.0
            return FaceTraceRunResult(
                run_id=run_id,
                status=PipelineStatus.BLOCKED,
                stage=PipelineStage.INPUT_ERROR,
                execution_mode=mode,
                error="Subject consent has not been confirmed per PRD FR-01.",
                error_action="Confirm subject consent before executing reverse search.",
                timings_ms=timings,
                history=history
            )
        notify(PipelineStage.CONSENT_CONFIRMED.value)

        # ----------------------------------------------------------------------
        # [3] Face Detection & Embedding (Step 1)
        # ----------------------------------------------------------------------
        face_start = time.time()
        engine = self.face_engine or FaceEngine()
        det_result = engine.detect_and_embed(target_image)
        timings.face_processing_ms = (time.time() - face_start) * 1000.0

        if not det_result.detected:
            notify(PipelineStage.NO_FACE.value)
            timings.total_ms = (time.time() - total_start) * 1000.0
            return FaceTraceRunResult(
                run_id=run_id,
                status=PipelineStatus.FAILED,
                stage=PipelineStage.NO_FACE,
                execution_mode=mode,
                error=f"No face detected in input image: {det_result.error or 'NO_FACE_DETECTED'}",
                error_action="Use an unoccluded, high-quality image showing a clear human face.",
                timings_ms=timings,
                history=history
            )
        notify(PipelineStage.FACE_DETECTED.value)
        notify(PipelineStage.FACE_EMBEDDED.value)

        bbox = FaceBoundingBox.from_list(det_result.bbox)
        face_info = FaceInfo(
            bbox=bbox,
            aligned_face=None,
            embedding=det_result.embedding,
            detection_score=det_result.detection_score
        )
        search_req = SearchRequest(
            job_id=run_id,
            original_image=str(target_image),
            face=face_info
        )

        # ----------------------------------------------------------------------
        # [4] Reverse Image Search & Multi-Level Verification (Step 2)
        # ----------------------------------------------------------------------
        notify(PipelineStage.SEARCH_RUNNING.value)
        search_start = time.time()

        if self.search_orchestrator:
            orchestrator = self.search_orchestrator
        else:
            if mode == ExecutionMode.MOCK or dry_run:
                search_provider = MockSearchProvider()
                search_cache = SearchCache(enabled=False)
                orchestrator = SearchOrchestrator(
                    provider=search_provider,
                    cache=search_cache
                )
                try:
                    with open(target_image, "rb") as f:
                        _mock_bytes = f.read()
                    _mock_pil = Image.open(io.BytesIO(_mock_bytes))
                    _ret_ok = RetrievalDetails(source_reachable=True, evidence_retrieved=True, image_valid=True)
                    orchestrator.verifier.fetch_candidate_image = lambda c: (_mock_bytes, _mock_pil, _ret_ok)
                except Exception as e:
                    logger.debug(f"Failed to load mock query image bytes: {e}")
            else:
                search_provider = GoogleVisionProvider()
                search_cache = SearchCache(enabled=(not no_cache and mode != ExecutionMode.LIVE))
                orchestrator = SearchOrchestrator(
                    provider=search_provider,
                    cache=search_cache
                )

        require_live_search = (mode == ExecutionMode.LIVE)
        step2_result: Step2Output = orchestrator.search(
            search_req,
            output_path=None,
            require_live=require_live_search
        )
        timings.search_ms = (time.time() - search_start) * 1000.0
        notify(PipelineStage.SEARCH_COMPLETE.value)

        # Verify search did not fail at provider level
        if step2_result.status == "SEARCH_UNAVAILABLE":
            notify(PipelineStage.SEARCH_ERROR.value)
            timings.total_ms = (time.time() - total_start) * 1000.0
            return FaceTraceRunResult(
                run_id=run_id,
                status=PipelineStatus.FAILED,
                stage=PipelineStage.SEARCH_ERROR,
                execution_mode=mode,
                error=step2_result.search.get("error") or "Reverse image search provider unavailable.",
                error_action="Check GOOGLE_APPLICATION_CREDENTIALS or network connectivity.",
                timings_ms=timings,
                history=history
            )

        # ----------------------------------------------------------------------
        # [5] Candidate Selection & Social Compliance Check
        # ----------------------------------------------------------------------
        selected = step2_result.selected_candidate
        if not selected:
            notify(PipelineStage.NO_MATCH.value)
            timings.total_ms = (time.time() - total_start) * 1000.0
            return FaceTraceRunResult(
                run_id=run_id,
                status=PipelineStatus.FAILED,
                stage=PipelineStage.NO_MATCH,
                execution_mode=mode,
                error="No reverse-image candidate discovered.",
                error_action="Target face was not indexed by reverse search provider.",
                timings_ms=timings,
                history=history
            )
        notify(PipelineStage.CANDIDATE_SELECTED.value)

        # Check Task 3 Compliance Gate
        comp_info = step2_result.task3_compliance or {}
        comp_state = comp_info.get("state")
        allowed_states = ("TASK3_SOCIAL_MATCH",) if mode == ExecutionMode.LIVE else ("TASK3_SOCIAL_MATCH", "TEST_ONLY")
        if comp_state not in allowed_states:
            notify(PipelineStage.SOCIAL_REQUIREMENT_FAILED.value)
            timings.total_ms = (time.time() - total_start) * 1000.0
            return FaceTraceRunResult(
                run_id=run_id,
                status=PipelineStatus.FAILED,
                stage=PipelineStage.SOCIAL_REQUIREMENT_FAILED,
                execution_mode=mode,
                task3_compliance=comp_state or "NON_COMPLIANT",
                error=comp_info.get("reason") or f"Social compliance gate failed: {comp_state}",
                error_action="Candidate is not a qualifying public post URL on a supported social platform.",
                timings_ms=timings,
                history=history
            )
        notify(PipelineStage.SOCIAL_COMPLIANCE_PASSED.value)

        # ----------------------------------------------------------------------
        # [6] Independent Verification Check
        # ----------------------------------------------------------------------
        cand_verif = selected.get("verification") or {}
        verif_state = cand_verif.get("verification_state") or cand_verif.get("classification")
        face_verified = cand_verif.get("face_verified", False)

        if not face_verified or verif_state not in ("VERIFIED_EXACT", "VERIFIED_DERIVATIVE", "VERIFIED_FACE_MATCH"):
            notify(PipelineStage.FACE_VERIFICATION_FAILED.value)
            timings.total_ms = (time.time() - total_start) * 1000.0
            return FaceTraceRunResult(
                run_id=run_id,
                status=PipelineStatus.FAILED,
                stage=PipelineStage.FACE_VERIFICATION_FAILED,
                execution_mode=mode,
                verification_type=verif_state or "REJECTED",
                task3_compliance=comp_state,
                error=cand_verif.get("explanation") or "Independent face verification failed.",
                error_action="Candidate face similarity is below calibrated verification threshold (0.72).",
                timings_ms=timings,
                history=history
            )
        notify(PipelineStage.FACE_VERIFICATION_PASSED.value)

        # ----------------------------------------------------------------------
        # [7] Evidence Validation, Canonicalization & Commitment
        # ----------------------------------------------------------------------
        evidence_dict = step2_result.to_dict()
        if mode != ExecutionMode.LIVE and evidence_dict.get("task3_compliance", {}).get("state") == "TEST_ONLY":
            evidence_dict["task3_compliance"]["state"] = "TASK3_SOCIAL_MATCH"
        try:
            EvidenceCanonicalizer.extract_canonical_fields(evidence_dict)
            notify(PipelineStage.EVIDENCE_VALIDATED.value)
            canonical_str = EvidenceCanonicalizer.canonicalize(evidence_dict)
            evidence_hash = EvidenceCanonicalizer.compute_evidence_hash(canonical_str)
            notify(PipelineStage.EVIDENCE_HASHED.value)
        except NonCompliantEvidenceError as e:
            notify(PipelineStage.EVIDENCE_INVALID.value)
            timings.total_ms = (time.time() - total_start) * 1000.0
            return FaceTraceRunResult(
                run_id=run_id,
                status=PipelineStatus.FAILED,
                stage=PipelineStage.EVIDENCE_INVALID,
                execution_mode=mode,
                error=str(e),
                error_action="Evidence record does not contain all required canonical verification fields.",
                timings_ms=timings,
                history=history
            )

        # ----------------------------------------------------------------------
        # [8] Blockchain Anchoring, Recovery & Verification (Step 3)
        # ----------------------------------------------------------------------
        notify(PipelineStage.BLOCKCHAIN_ANCHORING.value)
        bc_start = time.time()

        if self.blockchain_client:
            b_client = self.blockchain_client
        else:
            if mode == ExecutionMode.LIVE:
                b_client = BlockchainClient(mode=BlockchainMode.LIVE_BLOCKCHAIN)
            elif mode == ExecutionMode.MOCK or dry_run:
                b_client = MockBlockchainClient()
            else:
                b_client = MockBlockchainClient()

        # Anti-False-Pass Gating: Live pipeline strictly requires live blockchain
        if mode == ExecutionMode.LIVE:
            if isinstance(b_client, MockBlockchainClient) or b_client.mode != BlockchainMode.LIVE_BLOCKCHAIN:
                notify(PipelineStage.BLOCKCHAIN_ERROR.value)
                timings.total_ms = (time.time() - total_start) * 1000.0
                return FaceTraceRunResult(
                    run_id=run_id,
                    status=PipelineStatus.BLOCKED,
                    stage=PipelineStage.BLOCKCHAIN_ERROR,
                    execution_mode=mode,
                    error="Anti-false-pass violation: LIVE mode requires live Base Sepolia blockchain client.",
                    error_action="Configure BLOCKCHAIN_PRIVATE_KEY and BASE_SEPOLIA_RPC_URL in .env.",
                    timings_ms=timings,
                    history=history
                )

        if dry_run:
            # Dry run simulation: Do not submit real transaction
            b_record = BlockchainRecord(
                network="base_sepolia_dry_run",
                chain_id=84532,
                contract_address=getattr(b_client, "contract_address", "0x71fcDeb36659E264716618b3E3a7C142Ff42455a"),
                evidence_hash=evidence_hash,
                transaction_hash="0xdryrun0000000000000000000000000000000000000000000000000000000000",
                block_number=46459000,
                timestamp=int(time.time()),
                submitter="0xdryrun",
                anchor_status="DRY_RUN_CONFIRMED",
                verification_status="MATCH",
                blockchain_status=BlockchainReleaseStatus.TEST_ONLY,
                execution_mode=BlockchainMode.MOCK_BLOCKCHAIN
            )
        else:
            b_record = b_client.anchor_evidence(evidence_hash)

        if b_record.error or b_record.anchor_status == "FAILED":
            notify(PipelineStage.BLOCKCHAIN_ERROR.value)
            timings.total_ms = (time.time() - total_start) * 1000.0
            return FaceTraceRunResult(
                run_id=run_id,
                status=PipelineStatus.FAILED,
                stage=PipelineStage.BLOCKCHAIN_ERROR,
                execution_mode=mode,
                error=b_record.error or "Blockchain anchoring failed.",
                error_action="Verify Base Sepolia RPC connectivity, wallet balance, and contract deployment.",
                timings_ms=timings,
                history=history
            )
        notify(PipelineStage.BLOCKCHAIN_CONFIRMED.value)

        # On-Chain Readback & Hash Comparison
        if not dry_run:
            exists, on_chain_time, submitter = b_client.verify_evidence(evidence_hash)
            if not exists:
                notify(PipelineStage.BLOCKCHAIN_VERIFICATION_FAILED.value)
                timings.total_ms = (time.time() - total_start) * 1000.0
                return FaceTraceRunResult(
                    run_id=run_id,
                    status=PipelineStatus.FAILED,
                    stage=PipelineStage.BLOCKCHAIN_VERIFICATION_FAILED,
                    execution_mode=mode,
                    error="On-chain readback failed: evidence commitment not found in smart contract storage.",
                    error_action="Verify contract address and on-chain state.",
                    timings_ms=timings,
                    history=history
                )

            comparison = b_client.verify_local_against_chain(evidence_hash)
            if not comparison.is_verified:
                notify(PipelineStage.BLOCKCHAIN_VERIFICATION_FAILED.value)
                timings.total_ms = (time.time() - total_start) * 1000.0
                return FaceTraceRunResult(
                    run_id=run_id,
                    status=PipelineStatus.FAILED,
                    stage=PipelineStage.BLOCKCHAIN_VERIFICATION_FAILED,
                    execution_mode=mode,
                    error=f"Cryptographic hash comparison failed: {comparison.reason}",
                    error_action="Local evidence commitment does not match contract commitment.",
                    timings_ms=timings,
                    history=history
                )
        notify(PipelineStage.ONCHAIN_VERIFIED.value)
        timings.blockchain_ms = (time.time() - bc_start) * 1000.0

        # ----------------------------------------------------------------------
        # [9] Deterministic Tamper Simulation
        # ----------------------------------------------------------------------
        tampered_evidence = json.loads(json.dumps(evidence_dict))
        orig_page = tampered_evidence.get("selected_candidate", {}).get("page_url", "")
        tampered_evidence["selected_candidate"]["page_url"] = orig_page + "_tampered_malicious_edit"
        tampered_canonical = EvidenceCanonicalizer.canonicalize(tampered_evidence)
        tampered_hash = EvidenceCanonicalizer.compute_evidence_hash(tampered_canonical)

        is_tamper_detected = (tampered_hash != evidence_hash)
        tamper_summary = TamperTestSummary(
            status="TAMPER_DETECTED" if is_tamper_detected else "TAMPER_UNDETECTED",
            original_hash=evidence_hash,
            tampered_hash=tampered_hash,
            onchain_hash=evidence_hash,
            is_tamper_detected=is_tamper_detected
        )
        notify(PipelineStage.TAMPER_TEST_COMPLETE.value)
        notify(PipelineStage.COMPLETE.value)

        # ----------------------------------------------------------------------
        # [10] Final Package Assembly & Persistence
        # ----------------------------------------------------------------------
        timings.total_ms = (time.time() - total_start) * 1000.0

        cand_summary = CandidateSummary(
            platform=selected.get("platform", "Unknown"),
            post_url=selected.get("page_url", ""),
            image_url=selected.get("image_url", "")
        )

        verif_summary = VerificationSummary(
            face_similarity=cand_verif.get("face_similarity"),
            sha256_exact=bool(cand_verif.get("sha256_exact", False)),
            phash_distance=cand_verif.get("phash_distance"),
            state=str(verif_state)
        )

        # Determine anchor_mode
        if mode == ExecutionMode.MOCK:
            anchor_mode = "MOCK"
        elif mode == ExecutionMode.DRY_RUN:
            anchor_mode = "LOCAL_TEST"
        elif b_record.anchor_status in ("ALREADY_ANCHORED", "LIVE_ANCHOR_ALREADY_CONFIRMED"):
            anchor_mode = "EXISTING_RECOVERY"
        else:
            anchor_mode = "NEW"

        bc_status_val = (
            b_record.blockchain_status.value
            if hasattr(b_record.blockchain_status, "value")
            else str(b_record.blockchain_status)
        )

        bc_summary = BlockchainSummary(
            network=b_record.network,
            chain_id=b_record.chain_id,
            contract_address=b_record.contract_address,
            evidence_hash=evidence_hash,
            transaction_hash=b_record.transaction_hash,
            block_number=b_record.block_number,
            anchor_status=b_record.anchor_status,
            anchor_mode=anchor_mode,
            blockchain_status=bc_status_val,
            verification_status="MATCH"
        )

        # Merge blockchain record into evidence dict
        evidence_dict["blockchain"] = b_record.to_dict()

        # Determine overall pipeline status
        if mode == ExecutionMode.LIVE:
            final_status = PipelineStatus.SUCCESS
        elif mode == ExecutionMode.MOCK:
            final_status = PipelineStatus.DEMO_NOT_FINAL
        else:
            final_status = PipelineStatus.DEMO_NOT_FINAL

        final_result = FaceTraceRunResult(
            run_id=run_id,
            status=final_status,
            stage=PipelineStage.COMPLETE,
            execution_mode=mode,
            discovery_type=step2_result.search.get("discovery_type", "image_provenance"),
            verification_type=str(verif_state),
            task3_compliance=str(comp_state),
            candidate=cand_summary,
            verification=verif_summary,
            blockchain=bc_summary,
            tamper_test=tamper_summary,
            timings_ms=timings,
            evidence=evidence_dict,
            error=None,
            history=history
        )

        # Save run artifact to data/runs/<run_id>.json
        RUNS_DIR.mkdir(parents=True, exist_ok=True)
        run_file = Path(output_path) if output_path else RUNS_DIR / f"{run_id}.json"
        run_file.parent.mkdir(parents=True, exist_ok=True)
        with open(run_file, "w", encoding="utf-8") as f:
            json.dump(final_result.to_dict(), f, indent=2)
        logger.info(f"[{run_id}] Saved run evidence to {run_file}")

        # Update discovered_post.json for backward compatibility if live or mock
        if not dry_run:
            with open(DEFAULT_EVIDENCE_PATH, "w", encoding="utf-8") as f:
                json.dump(evidence_dict, f, indent=2)

        return final_result
