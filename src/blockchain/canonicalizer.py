"""
FaceTrace — Canonical Evidence Generator & Hasher
Produces deterministic, reproducible JSON representations and SHA-256 commitments.
"""

import hashlib
import json
from typing import Dict, Any, Union


class NonCompliantEvidenceError(ValueError):
    """Raised when evidence does not meet mandatory Task 3 compliance criteria."""
    pass


class EvidenceCanonicalizer:
    """
    Transforms validated Step 2 evidence packages into a stable, deterministic
    canonical JSON string and computes its 32-byte SHA-256 cryptographic commitment.
    """

    ALLOWED_COMPLIANCE_STATES = {"TASK3_SOCIAL_MATCH"}
    ALLOWED_VERIFICATION_STATES = {
        "VERIFIED_EXACT",
        "VERIFIED_DERIVATIVE",
        "VERIFIED_FACE_MATCH"
    }

    @classmethod
    def extract_canonical_fields(cls, evidence_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extracts only the stable fields required to prove the discovered evidence.
        Rejects non-qualifying or unverified evidence.
        """
        # Validate Task 3 compliance state
        compliance_info = evidence_data.get("task3_compliance", {})
        if isinstance(compliance_info, dict):
            comp_state = compliance_info.get("state")
        else:
            comp_state = str(compliance_info)

        if comp_state not in cls.ALLOWED_COMPLIANCE_STATES:
            raise NonCompliantEvidenceError(
                f"Evidence does not satisfy Task 3 compliance: state is '{comp_state}', "
                f"expected one of {cls.ALLOWED_COMPLIANCE_STATES}"
            )

        # Validate verification state
        selected = evidence_data.get("selected_candidate", {})
        if not selected:
            raise NonCompliantEvidenceError("Evidence contains no selected_candidate.")

        verification = selected.get("verification", {})
        verif_state = verification.get("verification_state") or verification.get("classification")
        if verif_state not in cls.ALLOWED_VERIFICATION_STATES:
            raise NonCompliantEvidenceError(
                f"Candidate verification state '{verif_state}' is not accepted for blockchain anchoring. "
                f"Expected one of {cls.ALLOWED_VERIFICATION_STATES}"
            )

        # Extract search provenance
        search_info = evidence_data.get("search", {})
        discovery_type = search_info.get("discovery_type", "image_provenance")
        execution_mode = search_info.get("execution_mode", "LIVE_EXTERNAL_SEARCH")

        # Extract face similarity
        face_sim = verification.get("face_similarity")
        if face_sim is not None:
            face_sim_val = round(float(face_sim), 4)
        else:
            face_sim_val = None

        # Build stable canonical dictionary
        canonical_dict = {
            "schema_version": str(evidence_data.get("schema_version", "1.0")),
            "discovery_type": str(discovery_type),
            "verification_type": str(verif_state),
            "task3_compliance": str(comp_state),
            "candidate_url": str(selected.get("page_url", "")).strip(),
            "candidate_image_url": str(selected.get("image_url", "")).strip(),
            "platform": str(selected.get("platform", "")).lower().strip(),
            "candidate_image_sha256": str(verification.get("sha256_candidate", "")).strip(),
            "candidate_image_phash": verification.get("phash_distance"),
            "face_similarity": face_sim_val,
            "execution_mode": str(execution_mode)
        }

        return canonical_dict

    @classmethod
    def canonicalize(cls, evidence_data: Dict[str, Any]) -> str:
        """
        Produces a deterministic, whitespace-normalized JSON string with sorted keys.
        """
        canonical_dict = cls.extract_canonical_fields(evidence_data)
        return json.dumps(
            canonical_dict,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False
        )

    @classmethod
    def compute_evidence_hash(cls, canonical_or_evidence: Union[str, Dict[str, Any]]) -> str:
        """
        Computes SHA-256 of the canonical representation, returned as '0x' prefixed 32-byte hex.
        """
        if isinstance(canonical_or_evidence, dict):
            canonical_str = cls.canonicalize(canonical_or_evidence)
        else:
            canonical_str = canonical_or_evidence

        digest = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
        return f"0x{digest}"
