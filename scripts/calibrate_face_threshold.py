#!/usr/bin/env python3
"""
FaceTrace ArcFace Threshold Calibration Harness.
Evaluates separation margin, false positive rate, and false negative rate across
same-person positive pairs and different-person negative pairs.
"""

from pathlib import Path
import sys
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
import io

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from src.core.face_engine import FaceEngine


def generate_variant(img_path: Path, transform_type: str) -> Image.Image:
    im = Image.open(img_path).convert("RGB")
    if transform_type == "resize_half":
        return im.resize((im.width // 2, im.height // 2), Image.Resampling.BILINEAR)
    elif transform_type == "jpeg_50":
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=50)
        buf.seek(0)
        return Image.open(buf).convert("RGB")
    elif transform_type == "brightness":
        enhancer = ImageEnhance.Brightness(im)
        return enhancer.enhance(1.2)
    elif transform_type == "contrast":
        enhancer = ImageEnhance.Contrast(im)
        return enhancer.enhance(1.2)
    elif transform_type == "blur":
        return im.filter(ImageFilter.GaussianBlur(radius=1.0))
    return im


def run_calibration(target_threshold: float = 0.72):
    print("=" * 80)
    print("          FACETRACE ARCFACE SIMILARITY THRESHOLD CALIBRATION HARNESS")
    print(f"                     Evaluating Target Threshold: {target_threshold}")
    print("=" * 80)

    engine = FaceEngine(model_name="buffalo_sc")
    engine._ensure_initialized()

    # Load base faces
    base_images = {
        "craig": Path("samples/daniel_craig.jpg"),
        "craig_crop": Path("samples/daniel_craig_crop.jpg"),
        "craig_flip": Path("samples/daniel_craig_flipped.jpg"),
        "udit": Path("samples/udit.jpg"),
        "t1_person": Path("samples/t1_person.jpg")
    }

    # Extract embeddings for base images
    embeddings = {}
    for name, p in base_images.items():
        if p.exists():
            det = engine.detect_and_embed(p)
            if det.detected and det.embedding is not None:
                emb = np.asarray(det.embedding, dtype=np.float32).flatten()
                norm = np.linalg.norm(emb)
                if norm > 0:
                    emb = emb / norm
                embeddings[name] = emb

    # Generate additional positive variants
    positive_pairs = []
    if "craig" in embeddings:
        craig_emb = embeddings["craig"]
        # 1. Craig original vs Craig crop
        if "craig_crop" in embeddings:
            sim = float(np.dot(craig_emb, embeddings["craig_crop"]))
            positive_pairs.append(("Daniel Craig vs Craig Crop", sim))

        # 2. Craig original vs Craig flipped
        if "craig_flip" in embeddings:
            sim = float(np.dot(craig_emb, embeddings["craig_flip"]))
            positive_pairs.append(("Daniel Craig vs Craig Flipped", sim))

        # 3. Craig vs JPEG quality 50
        im_jpg = generate_variant(base_images["craig"], "jpeg_50")
        bgr = engine.load_image_bgr(im_jpg)
        f = engine._app.get(bgr)
        if f and f[0].embedding is not None:
            e = f[0].embedding / np.linalg.norm(f[0].embedding)
            positive_pairs.append(("Daniel Craig vs JPEG Q50", float(np.dot(craig_emb, e))))

        # 4. Craig vs Resize Half
        im_res = generate_variant(base_images["craig"], "resize_half")
        bgr = engine.load_image_bgr(im_res)
        f = engine._app.get(bgr)
        if f and f[0].embedding is not None:
            e = f[0].embedding / np.linalg.norm(f[0].embedding)
            positive_pairs.append(("Daniel Craig vs Resized 50%", float(np.dot(craig_emb, e))))

        # 5. Craig vs Brightness
        im_b = generate_variant(base_images["craig"], "brightness")
        bgr = engine.load_image_bgr(im_b)
        f = engine._app.get(bgr)
        if f and f[0].embedding is not None:
            e = f[0].embedding / np.linalg.norm(f[0].embedding)
            positive_pairs.append(("Daniel Craig vs Brightness +20%", float(np.dot(craig_emb, e))))

        # 6. Craig vs Contrast
        im_c = generate_variant(base_images["craig"], "contrast")
        bgr = engine.load_image_bgr(im_c)
        f = engine._app.get(bgr)
        if f and f[0].embedding is not None:
            e = f[0].embedding / np.linalg.norm(f[0].embedding)
            positive_pairs.append(("Daniel Craig vs Contrast +20%", float(np.dot(craig_emb, e))))

        # 7. Craig vs Gaussian Blur
        im_bl = generate_variant(base_images["craig"], "blur")
        bgr = engine.load_image_bgr(im_bl)
        f = engine._app.get(bgr)
        if f and f[0].embedding is not None:
            e = f[0].embedding / np.linalg.norm(f[0].embedding)
            positive_pairs.append(("Daniel Craig vs Mild Blur", float(np.dot(craig_emb, e))))

    if "udit" in embeddings:
        u_emb = embeddings["udit"]
        # 8. Udit vs JPEG Q50
        im_u_jpg = generate_variant(base_images["udit"], "jpeg_50")
        bgr = engine.load_image_bgr(im_u_jpg)
        f = engine._app.get(bgr)
        if f and f[0].embedding is not None:
            e = f[0].embedding / np.linalg.norm(f[0].embedding)
            positive_pairs.append(("Subject Udit vs JPEG Q50", float(np.dot(u_emb, e))))

        # 9. Udit vs Resized Half
        im_u_res = generate_variant(base_images["udit"], "resize_half")
        bgr = engine.load_image_bgr(im_u_res)
        f = engine._app.get(bgr)
        if f and f[0].embedding is not None:
            e = f[0].embedding / np.linalg.norm(f[0].embedding)
            positive_pairs.append(("Subject Udit vs Resized 50%", float(np.dot(u_emb, e))))

    # Extract all faces from group photo (Friends cast) for negative pairs
    negative_pairs = []
    t1_bgr = engine.load_image_bgr(Image.open(base_images["t1_person"]))
    group_faces = engine._app.get(t1_bgr)
    group_embs = []
    for gf in group_faces:
        if gf.embedding is not None:
            ge = gf.embedding / np.linalg.norm(gf.embedding)
            group_embs.append(ge)

    # 1. Craig vs Udit
    if "craig" in embeddings and "udit" in embeddings:
        sim = float(np.dot(embeddings["craig"], embeddings["udit"]))
        negative_pairs.append(("Daniel Craig vs Subject Udit", sim))

    # 2. Craig vs T1 person
    if "craig" in embeddings and "t1_person" in embeddings:
        sim = float(np.dot(embeddings["craig"], embeddings["t1_person"]))
        negative_pairs.append(("Daniel Craig vs T1 Person", sim))

    # 3. Udit vs T1 person
    if "udit" in embeddings and "t1_person" in embeddings:
        sim = float(np.dot(embeddings["udit"], embeddings["t1_person"]))
        negative_pairs.append(("Subject Udit vs T1 Person", sim))

    # 4-8. Craig vs Friends group cast members
    if "craig" in embeddings:
        for idx, ge in enumerate(group_embs[:5]):
            sim = float(np.dot(embeddings["craig"], ge))
            negative_pairs.append((f"Daniel Craig vs Group Member #{idx+1}", sim))

    # 9-11. Udit vs Friends group cast members
    if "udit" in embeddings:
        for idx, ge in enumerate(group_embs[:3]):
            sim = float(np.dot(embeddings["udit"], ge))
            negative_pairs.append((f"Subject Udit vs Group Member #{idx+1}", sim))

    # --------------------------------------------------------------------------
    # COMPUTE CALIBRATION STATISTICS
    # --------------------------------------------------------------------------
    pos_sims = [p[1] for p in positive_pairs]
    neg_sims = [n[1] for n in negative_pairs]

    pos_mean = np.mean(pos_sims)
    neg_mean = np.mean(neg_sims)
    pos_min = np.min(pos_sims)
    neg_max = np.max(neg_sims)

    false_positives = sum(1 for s in neg_sims if s >= target_threshold)
    false_negatives = sum(1 for s in pos_sims if s < target_threshold)
    separation_margin = pos_min - neg_max

    print("\n--- POSITIVE PAIRS (Same Person, Transformed/Augmented) ---")
    for label, s in positive_pairs:
        status = "PASS" if s >= target_threshold else "FAIL (FN)"
        print(f"  {label:<38} Similarity: {s:+.4f}  [{status}]")

    print("\n--- NEGATIVE PAIRS (Different People) ---")
    for label, s in negative_pairs:
        status = "PASS (Rejected)" if s < target_threshold else "FAIL (FP)"
        print(f"  {label:<38} Similarity: {s:+.4f}  [{status}]")

    print("\n" + "=" * 80)
    print("                    CALIBRATION SUMMARY METRICS")
    print("=" * 80)
    print(f"Total Positive Pairs:        {len(pos_sims)}")
    print(f"Total Negative Pairs:        {len(neg_sims)}")
    print(f"Positive Mean Similarity:    {pos_mean:.4f}")
    print(f"Negative Mean Similarity:    {neg_mean:.4f}")
    print(f"Minimum Positive Similarity: {pos_min:.4f}")
    print(f"Maximum Negative Similarity: {neg_max:.4f}")
    print(f"Separation Margin (MinP-MaxN): {separation_margin:+.4f}")
    print(f"Target Threshold:            {target_threshold:.2f}")
    print(f"False Positives:             {false_positives} ({false_positives / len(neg_sims) * 100:.1f}%)")
    print(f"False Negatives:             {false_negatives} ({false_negatives / len(pos_sims) * 100:.1f}%)")
    print("-" * 80)

    if false_positives == 0 and false_negatives == 0 and separation_margin > 0:
        print(f"[DECISION] VALIDATED: Threshold {target_threshold} provides 0% error rate with a positive separation margin (+{separation_margin:.4f}).")
        print("           No threshold modification is required.")
    else:
        rec = (pos_min + neg_max) / 2.0
        print(f"[DECISION] SUGGESTION: Optimal midpoint threshold is {rec:.4f}.")

    print("=" * 80)


if __name__ == "__main__":
    run_calibration()
