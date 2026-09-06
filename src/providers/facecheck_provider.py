"""
FaceCheck.ID API provider implementation.
Performs genuine reverse face searches via FaceCheck REST API.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional
import logging
import time
import requests

logger = logging.getLogger(__name__)


from urllib.parse import urlparse


@dataclass
class DiscoveredCandidate:
    candidate_id: str
    source_url: str
    provider: str = "facecheck"
    provider_score: int = 0  # 0 to 100
    thumbnail_base64: Optional[str] = None
    raw_metadata: Dict[str, Any] = field(default_factory=dict)
    is_demo: bool = False

    def is_external_source(self) -> bool:
        """
        Validates that candidate source_url points to a genuine external web page,
        and is not a placeholder link pointing back to facecheck.id itself.
        """
        if not self.source_url or not self.source_url.startswith(("http://", "https://")):
            return False
        netloc = urlparse(self.source_url).netloc.lower()
        # Exclude internal facecheck.id placeholder links
        if netloc in ("facecheck.id", "www.facecheck.id", "staging.facecheck.id"):
            return False
        return True


@dataclass
class SearchResult:
    success: bool
    case_id: Optional[str] = None
    candidates: List[DiscoveredCandidate] = field(default_factory=list)
    error: Optional[str] = None
    error_code: Optional[str] = None
    progress: int = 0
    message: Optional[str] = None
    is_demo: bool = False


class FaceCheckProvider:
    """Client for genuine FaceCheck.ID REST API."""

    def __init__(self, api_token: Optional[str] = None, demo_mode: bool = True, base_url: str = "https://facecheck.id"):
        self.api_token = api_token or ""
        self.demo_mode = demo_mode
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept": "application/json",
        })
        if self.api_token:
            self.session.headers.update({"Authorization": self.api_token})

    def get_info(self) -> Dict[str, Any]:
        """Returns remaining search credits, online status, and indexed face count."""
        url = f"{self.base_url}/api/info"
        try:
            resp = self.session.post(url, json={}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "success": True,
                    "credits": data.get("credits", 0),
                    "online": data.get("online", False),
                    "face_count": data.get("facecount", 0),
                    "message": data.get("message"),
                    "raw": data
                }
            return {
                "success": False,
                "error": f"HTTP {resp.status_code}: {resp.text}",
                "code": f"HTTP_{resp.status_code}"
            }
        except Exception as e:
            return {"success": False, "error": str(e), "code": "NETWORK_ERROR"}

    def upload_image(self, image_path: Path) -> Dict[str, Any]:
        """Uploads an image to FaceCheck and returns the search session info."""
        if not self.api_token:
            return {
                "success": False,
                "error": "FaceCheck API token is missing. Please set FACECHECK_API_TOKEN in .env",
                "code": "MISSING_API_TOKEN"
            }

        url = f"{self.base_url}/api/upload_pic"
        logger.info(f"Uploading image {image_path.name} to {url}...")

        try:
            with open(image_path, "rb") as f:
                files = {
                    "images": (image_path.name, f, "image/jpeg"),
                    "id_search": (None, "")
                }
                resp = self.session.post(url, files=files, timeout=30)

            if resp.status_code == 403:
                return {
                    "success": False,
                    "error": "HTTP 403 Forbidden: WAF or IP restriction on FaceCheck.ID.",
                    "code": "HTTP_403"
                }

            data = resp.json()
            if data.get("error"):
                return {
                    "success": False,
                    "error": data["error"],
                    "code": data.get("code", "API_ERROR")
                }

            id_search = data.get("id_search")
            if not id_search:
                return {
                    "success": False,
                    "error": "No id_search returned in upload response.",
                    "code": "NO_SEARCH_ID"
                }

            return {
                "success": True,
                "id_search": id_search,
                "message": data.get("message", "Upload successful")
            }

        except requests.RequestException as e:
            logger.error(f"Network error during upload: {e}")
            return {
                "success": False,
                "error": f"Network error during upload: {e}",
                "code": "NETWORK_ERROR"
            }

    def poll_search(self, id_search: str, max_wait_seconds: int = 120, poll_interval: float = 2.0) -> SearchResult:
        """Polls the FaceCheck search endpoint until completion or timeout."""
        url = f"{self.base_url}/api/search"
        payload = {
            "id_search": id_search,
            "with_progress": True,
            "status_only": False,
            "demo": self.demo_mode
        }

        start_time = time.time()
        logger.info(f"Initiating search poll for id_search={id_search} (demo_mode={self.demo_mode})...")

        while (time.time() - start_time) < max_wait_seconds:
            try:
                resp = self.session.post(url, json=payload, timeout=20)
                if resp.status_code != 200:
                    return SearchResult(
                        success=False,
                        error=f"Search request failed with HTTP {resp.status_code}",
                        error_code=f"HTTP_{resp.status_code}"
                    )

                data = resp.json()
                if data.get("error"):
                    return SearchResult(
                        success=False,
                        error=data["error"],
                        error_code=data.get("code", "SEARCH_ERROR")
                    )

                progress = data.get("progress", 0)
                message = data.get("message", "")
                logger.info(f"Search progress: {progress}% - {message}")

                # Output items available
                output = data.get("output")
                if output and "items" in output:
                    raw_items = output["items"] or []
                    candidates: List[DiscoveredCandidate] = []
                    for idx, item in enumerate(raw_items):
                        candidates.append(
                            DiscoveredCandidate(
                                candidate_id=item.get("guid") or f"cand_{idx}",
                                source_url=item.get("url", ""),
                                provider="facecheck",
                                provider_score=int(item.get("score", 0)),
                                thumbnail_base64=item.get("base64"),
                                raw_metadata=item,
                                is_demo=self.demo_mode
                            )
                        )

                    return SearchResult(
                        success=True,
                        case_id=id_search,
                        candidates=candidates,
                        progress=100,
                        message="Search completed successfully",
                        is_demo=self.demo_mode
                    )

                time.sleep(poll_interval)

            except requests.RequestException as e:
                logger.warning(f"Transient polling error: {e}. Retrying in {poll_interval}s...")
                time.sleep(poll_interval)

        return SearchResult(
            success=False,
            case_id=id_search,
            error=f"Search timed out after {max_wait_seconds} seconds.",
            error_code="TIMEOUT"
        )
