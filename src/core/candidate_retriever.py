"""
Candidate evidence and image retrieval engine.
Retrieves and decodes candidate image data from search responses or remote web targets.
"""

from dataclasses import dataclass
from typing import Optional
import base64
import io
import logging
import requests
from PIL import Image

from ..providers.facecheck_provider import DiscoveredCandidate

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    status: str  # RETRIEVED | UNREACHABLE | NO_USABLE_IMAGE | INVALID_FORMAT
    image_bytes: Optional[bytes] = None
    pil_image: Optional[Image.Image] = None
    content_type: Optional[str] = None
    error: Optional[str] = None


class CandidateRetriever:
    """Retrieves candidate face images from thumbnails or external URLs."""

    def __init__(self, timeout_seconds: int = 15):
        self.timeout = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        })

    def decode_thumbnail_base64(self, raw_base64: str) -> RetrievalResult:
        """Decodes base64 thumbnail string into PIL Image and raw bytes."""
        try:
            # Handle possible data URL or whitespace prefix
            clean_b64 = raw_base64.strip()
            if "," in clean_b64 and "base64" in clean_b64:
                clean_b64 = clean_b64.split(",", 1)[1]
            elif " " in clean_b64:
                clean_b64 = clean_b64.split(" ", 1)[1]

            img_bytes = base64.b64decode(clean_b64)
            pil_img = Image.open(io.BytesIO(img_bytes))
            pil_img.verify()  # Verify integrity

            # Re-open after verify()
            pil_img = Image.open(io.BytesIO(img_bytes))

            return RetrievalResult(
                status="RETRIEVED",
                image_bytes=img_bytes,
                pil_image=pil_img,
                content_type=pil_img.format
            )
        except Exception as e:
            logger.warning(f"Failed to decode base64 thumbnail: {e}")
            return RetrievalResult(
                status="NO_USABLE_IMAGE",
                error=f"Base64 decode failed: {str(e)}"
            )

    def fetch_from_url(self, url: str) -> RetrievalResult:
        """Attempts to fetch candidate image directly from external URL."""
        if not url or not url.startswith(("http://", "https://")):
            return RetrievalResult(
                status="UNREACHABLE",
                error=f"Invalid URL: {url}"
            )

        try:
            resp = self.session.get(url, timeout=self.timeout, stream=True)
            if resp.status_code != 200:
                return RetrievalResult(
                    status="UNREACHABLE",
                    error=f"HTTP status {resp.status_code} while fetching {url}"
                )

            img_bytes = resp.content
            pil_img = Image.open(io.BytesIO(img_bytes))
            pil_img.verify()
            pil_img = Image.open(io.BytesIO(img_bytes))

            return RetrievalResult(
                status="RETRIEVED",
                image_bytes=img_bytes,
                pil_image=pil_img,
                content_type=resp.headers.get("Content-Type", pil_img.format)
            )
        except Exception as e:
            logger.warning(f"Could not retrieve candidate image from URL {url}: {e}")
            return RetrievalResult(
                status="UNREACHABLE",
                error=f"Fetch failed: {str(e)}"
            )

    def retrieve_candidate(self, candidate: DiscoveredCandidate) -> RetrievalResult:
        """
        Primary entry point: attempts to decode embedded thumbnail first,
        falling back to URL fetch if thumbnail is unavailable.
        """
        if candidate.thumbnail_base64:
            res = self.decode_thumbnail_base64(candidate.thumbnail_base64)
            if res.status == "RETRIEVED":
                return res

        # Fallback to source URL if applicable
        if candidate.source_url:
            return self.fetch_from_url(candidate.source_url)

        return RetrievalResult(
            status="NO_USABLE_IMAGE",
            error="Candidate contains neither valid thumbnail nor reachable image URL."
        )
