"""
Query Variant Generator for Step 2 Reverse Search.
Produces Query A (Original Image) and Query B (Raw Padded Face Crop).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import logging
from PIL import Image

from .models import FaceBoundingBox

logger = logging.getLogger(__name__)


@dataclass
class GeneratedVariants:
    original_path: Path
    face_crop_path: Path
    crop_bbox_used: FaceBoundingBox
    is_temporary_crop: bool = True

    def cleanup(self):
        """Removes temporary crop image if created."""
        if self.is_temporary_crop and self.face_crop_path.exists():
            try:
                self.face_crop_path.unlink()
                logger.debug(f"Cleaned up temporary query crop: {self.face_crop_path}")
            except Exception as e:
                logger.warning(f"Could not remove temp crop {self.face_crop_path}: {e}")


class QueryVariantGenerator:
    """
    Generates retrieval query variants from Step 1 input.
    Query A = Original image
    Query B = Raw padded face crop (20-30% margin, avoiding geometric warp)
    """

    def __init__(self, padding_ratio: float = 0.25, temp_dir: Optional[Path] = None):
        """
        :param padding_ratio: Percentage margin to add around face bounding box (default 0.25 = 25%)
        :param temp_dir: Directory where temporary crops are written (default data/temp)
        """
        self.padding_ratio = padding_ratio
        default_temp = Path(__file__).resolve().parent.parent.parent / "data" / "temp"
        self.temp_dir = temp_dir or default_temp
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, original_image_path: Path, bbox: FaceBoundingBox, job_id: str = "query") -> GeneratedVariants:
        """
        Generates Query A and Query B.
        """
        if not original_image_path.exists():
            raise FileNotFoundError(f"Original image not found: {original_image_path}")

        # Query A is the original uncropped image
        query_a_path = original_image_path.resolve()

        # Query B: Generate raw padded face crop
        with Image.open(query_a_path) as im:
            img_w, img_h = im.size

            # Compute padding in pixels
            pad_w = bbox.width * self.padding_ratio
            pad_h = bbox.height * self.padding_ratio

            # Padded coordinates clamped to image borders
            crop_x1 = max(0, int(round(bbox.x - pad_w)))
            crop_y1 = max(0, int(round(bbox.y - pad_h)))
            crop_x2 = min(img_w, int(round(bbox.x + bbox.width + pad_w)))
            crop_y2 = min(img_h, int(round(bbox.y + bbox.height + pad_h)))

            crop_box = (crop_x1, crop_y1, crop_x2, crop_y2)
            cropped_im = im.crop(crop_box)

            # Ensure RGB format for query upload
            if cropped_im.mode in ("RGBA", "LA", "P"):
                bg = Image.new("RGBA", cropped_im.size, (255, 255, 255, 255))
                cropped_im = Image.alpha_composite(bg, cropped_im.convert("RGBA")).convert("RGB")
            elif cropped_im.mode != "RGB":
                cropped_im = cropped_im.convert("RGB")

            crop_filename = f"{job_id}_face_crop_pad{int(self.padding_ratio*100)}.jpg"
            query_b_path = (self.temp_dir / crop_filename).resolve()
            cropped_im.save(query_b_path, format="JPEG", quality=95)

        logger.info(
            f"[Query Variants] Generated Query A (original: {img_w}x{img_h}) and "
            f"Query B (padded crop: {crop_x2 - crop_x1}x{crop_y2 - crop_y1}, margin={int(self.padding_ratio*100)}%)"
        )

        return GeneratedVariants(
            original_path=query_a_path,
            face_crop_path=query_b_path,
            crop_bbox_used=FaceBoundingBox(
                x=crop_x1,
                y=crop_y1,
                width=crop_x2 - crop_x1,
                height=crop_y2 - crop_y1
            ),
            is_temporary_crop=True
        )
