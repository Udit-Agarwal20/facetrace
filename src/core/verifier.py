"""
Independent face verification and similarity scoring module.
Calculates cosine similarity and applies calibrated thresholds.
"""

from dataclasses import dataclass
from typing import Optional
import numpy as np


@dataclass
class VerificationDecision:
    similarity: float
    threshold: float
    decision: str  # ACCEPTED | REJECTED | INCONCLUSIVE
    detection_score: float
    provider_score: int
    candidate_id: str
    source_url: str
    explanation: str


class FaceVerifier:
    """Performs independent local verification between query and candidate face embeddings."""

    def __init__(self, threshold: float = 0.72, inconclusive_lower_bound: float = 0.50):
        self.threshold = threshold
        self.inconclusive_lower_bound = inconclusive_lower_bound

    @staticmethod
    def compute_cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """Computes cosine similarity between two embedding vectors."""
        a = np.asarray(vec_a, dtype=np.float32).flatten()
        b = np.asarray(vec_b, dtype=np.float32).flatten()

        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0

        sim = float(np.dot(a, b) / (norm_a * norm_b))
        # Clamp to [-1.0, 1.0] to avoid float precision anomalies
        return max(-1.0, min(1.0, sim))

    def evaluate(
        self,
        query_embedding: np.ndarray,
        candidate_embedding: np.ndarray,
        candidate_id: str,
        source_url: str,
        candidate_detection_score: float,
        provider_score: int
    ) -> VerificationDecision:
        """
        Independently compares query and candidate embeddings,
        emitting an explainable verification verdict.
        """
        similarity = self.compute_cosine_similarity(query_embedding, candidate_embedding)

        if similarity >= self.threshold:
            decision = "ACCEPTED"
            explanation = (
                f"Local similarity ({similarity:.4f}) meets or exceeds calibrated threshold ({self.threshold:.2f}). "
                f"Independent verification confirmed."
            )
        elif similarity >= self.inconclusive_lower_bound:
            decision = "INCONCLUSIVE"
            explanation = (
                f"Local similarity ({similarity:.4f}) is below acceptance threshold ({self.threshold:.2f}) "
                f"but exceeds minimum noise floor ({self.inconclusive_lower_bound:.2f}). Result is ambiguous."
            )
        else:
            decision = "REJECTED"
            explanation = (
                f"Local similarity ({similarity:.4f}) is substantially below threshold ({self.threshold:.2f}). "
                f"Candidate face does not match input subject."
            )

        return VerificationDecision(
            similarity=round(similarity, 4),
            threshold=self.threshold,
            decision=decision,
            detection_score=round(candidate_detection_score, 4),
            provider_score=provider_score,
            candidate_id=candidate_id,
            source_url=source_url,
            explanation=explanation
        )
