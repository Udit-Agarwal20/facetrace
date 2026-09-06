"""
Face detection and ArcFace embedding engine using InsightFace.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union, List
import io
import logging
import numpy as np
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)


@dataclass
class FaceDetectionResult:
    detected: bool
    num_faces: int = 0
    bbox: Optional[List[float]] = None
    detection_score: float = 0.0
    embedding: Optional[np.ndarray] = None
    error: Optional[str] = None


class FaceEngine:
    """Encapsulates InsightFace detection and ArcFace embedding extraction."""

    def __init__(self, model_name: str = "buffalo_sc", ctx_id: int = -1, det_size: tuple = (640, 640)):
        """
        Initialize InsightFace FaceAnalysis engine.

        :param model_name: Name of model bundle (default 'buffalo_sc' for CPU/MPS efficiency)
        :param ctx_id: -1 for CPU, 0+ for GPU
        :param det_size: detection input resolution
        """
        self.model_name = model_name
        self.ctx_id = ctx_id
        self.det_size = det_size
        self._app = None

    def _ensure_initialized(self):
        if self._app is None:
            try:
                import insightface
                from insightface.app import FaceAnalysis

                logger.info(f"Initializing InsightFace model bundle: {self.model_name}")
                app = FaceAnalysis(name=self.model_name)
                app.prepare(ctx_id=self.ctx_id, det_size=self.det_size)
                self._app = app
                logger.info("InsightFace FaceAnalysis engine ready.")
            except Exception as e:
                logger.error(f"Failed to initialize InsightFace: {e}")
                raise RuntimeError(f"Could not load InsightFace model '{self.model_name}': {e}") from e

    @staticmethod
    def load_image_bgr(image_input: Union[str, Path, bytes, Image.Image, np.ndarray]) -> np.ndarray:
        """
        Loads any supported image input into BGR uint8 numpy array for InsightFace.
        Safely handles palette ('P') and alpha transparency ('RGBA', 'LA') images.
        Logs detailed metadata (mode, width, height, channels, dtype, min/max).
        """
        raw_mode = None
        orig_size = None

        if isinstance(image_input, np.ndarray):
            raw_mode = f"ndarray_{image_input.shape}"
            orig_size = (image_input.shape[1], image_input.shape[0]) if image_input.ndim >= 2 else (0, 0)
            if image_input.ndim != 3 or image_input.shape[2] not in (3, 4):
                raise ValueError(f"Invalid image array shape: {image_input.shape}")
            if image_input.shape[2] == 4:
                # RGBA numpy array -> convert to BGR via alpha blend on white
                import cv2
                rgba = image_input.astype(np.float32)
                alpha = rgba[:, :, 3:4] / 255.0
                rgb = rgba[:, :, :3]
                white_bg = np.ones_like(rgb) * 255.0
                blended_rgb = (rgb * alpha + white_bg * (1.0 - alpha)).astype(np.uint8)
                bgr_arr = cv2.cvtColor(blended_rgb, cv2.COLOR_RGB2BGR)
            else:
                bgr_arr = image_input.copy()
        else:
            if isinstance(image_input, (str, Path)):
                path = Path(image_input)
                if not path.exists():
                    raise FileNotFoundError(f"Image file not found: {path}")
                with open(path, "rb") as f:
                    pil_img = Image.open(io.BytesIO(f.read()))
            elif isinstance(image_input, bytes):
                pil_img = Image.open(io.BytesIO(image_input))
            elif isinstance(image_input, Image.Image):
                pil_img = image_input
            else:
                raise TypeError(f"Unsupported image input type: {type(image_input)}")

            try:
                pil_img = ImageOps.exif_transpose(pil_img)
            except Exception:
                pass

            raw_mode = pil_img.mode
            orig_size = pil_img.size
            has_transparency = ("transparency" in pil_img.info) or (pil_img.mode in ("RGBA", "LA")) or (pil_img.mode == "P" and "transparency" in pil_img.info)

            # Explicitly handle palette and transparency
            if pil_img.mode == "P":
                # Convert palette to RGBA first to prevent 'Transparency expressed in bytes' warning
                rgba_img = pil_img.convert("RGBA")
                bg = Image.new("RGBA", rgba_img.size, (255, 255, 255, 255))
                pil_img = Image.alpha_composite(bg, rgba_img).convert("RGB")
            elif pil_img.mode in ("RGBA", "LA") or has_transparency:
                rgba_img = pil_img.convert("RGBA")
                bg = Image.new("RGBA", rgba_img.size, (255, 255, 255, 255))
                pil_img = Image.alpha_composite(bg, rgba_img).convert("RGB")
            elif pil_img.mode != "RGB":
                pil_img = pil_img.convert("RGB")

            rgb_arr = np.array(pil_img, dtype=np.uint8)
            # RGB to BGR for OpenCV / InsightFace
            bgr_arr = rgb_arr[:, :, ::-1].copy()

        bgr_arr = np.ascontiguousarray(bgr_arr, dtype=np.uint8)
        h, w, c = bgr_arr.shape
        min_val = int(bgr_arr.min())
        max_val = int(bgr_arr.max())

        logger.info(
            f"[Image Preprocessing] Raw Mode: {raw_mode} -> BGR | "
            f"Dimensions: {w}x{h} | Channels: {c} | Dtype: {bgr_arr.dtype} | "
            f"Pixel Range: [{min_val}, {max_val}]"
        )

        return bgr_arr

    def detect_and_embed(self, image_input: Union[str, Path, bytes, Image.Image, np.ndarray]) -> FaceDetectionResult:
        """
        Detects faces and extracts ArcFace embedding for the most prominent face.
        """
        self._ensure_initialized()

        try:
            img_bgr = self.load_image_bgr(image_input)
        except Exception as e:
            return FaceDetectionResult(
                detected=False,
                error=f"INVALID_INPUT: {str(e)}"
            )

        try:
            faces = self._app.get(img_bgr)
        except Exception as e:
            return FaceDetectionResult(
                detected=False,
                error=f"DETECTION_FAILED: {str(e)}"
            )

        if not faces:
            return FaceDetectionResult(
                detected=False,
                num_faces=0,
                error="NO_FACE_DETECTED"
            )

        # Sort by detection score or face area (highest score first)
        faces_sorted = sorted(faces, key=lambda f: float(getattr(f, "det_score", 0.0)), reverse=True)
        primary_face = faces_sorted[0]

        embedding = primary_face.embedding
        if embedding is not None:
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm  # Unit normalized

        bbox = primary_face.bbox.tolist() if hasattr(primary_face, "bbox") and primary_face.bbox is not None else None
        det_score = float(getattr(primary_face, "det_score", 0.0))

        return FaceDetectionResult(
            detected=True,
            num_faces=len(faces),
            bbox=bbox,
            detection_score=det_score,
            embedding=embedding,
            error=None
        )
