"""
Image alignment pipeline using SIFT + FLANN + affine estimation.

Uses affine transforms (6 DOF) instead of full homography (8 DOF) to avoid
wild perspective distortions. Falls back to chain alignment through temporal
neighbors when direct-to-reference matching fails. Validates all transforms
geometrically before accepting.

Output resolution matches the reference image (1500px long side).
"""

import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

# --- Configuration ---
OUTPUT_LONG_SIDE = 1500
SIFT_NFEATURES = 8000
FLANN_TREES = 5
FLANN_CHECKS = 200
LOWE_RATIO = 0.75
RANSAC_REPROJ_THRESHOLD = 5.0
MIN_GOOD_MATCHES = 15
MIN_INLIERS = 20

# Geometric validation thresholds
MAX_ROTATION_DEG = 12.0
MAX_SCALE_DEVIATION = 0.25  # allow 0.75x to 1.25x scale
MAX_TRANSLATION_FRAC = 0.30  # max 30% of image dimension shift

# Canvas padding around reference frame (fraction of ref dimensions)
CANVAS_PADDING_FRAC = 0.10


def load_image(path: Path) -> np.ndarray:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Could not load image: {path}")
    return img


def resize_to_reference(img: np.ndarray, ref_h: int, ref_w: int) -> np.ndarray:
    """Resize image to match reference dimensions for consistent feature matching."""
    h, w = img.shape[:2]
    if h == ref_h and w == ref_w:
        return img
    return cv2.resize(img, (ref_w, ref_h), interpolation=cv2.INTER_LANCZOS4)


def detect_and_compute(sift: cv2.SIFT, img: np.ndarray):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    kp, des = sift.detectAndCompute(gray, None)
    return kp, des


def match_descriptors(des_a: np.ndarray, des_b: np.ndarray):
    """Match descriptors using FLANN with Lowe's ratio test."""
    if des_a is None or des_b is None:
        return []
    if len(des_a) < 2 or len(des_b) < 2:
        return []

    index_params = dict(algorithm=1, trees=FLANN_TREES)
    search_params = dict(checks=FLANN_CHECKS)
    flann = cv2.FlannBasedMatcher(index_params, search_params)

    matches = flann.knnMatch(des_b, des_a, k=2)

    good = []
    for pair in matches:
        if len(pair) == 2:
            m, n = pair
            if m.distance < LOWE_RATIO * n.distance:
                good.append(m)
    return good


def estimate_affine(kp_ref, kp_query, good_matches):
    """Estimate affine transform from query to reference using RANSAC."""
    if len(good_matches) < MIN_GOOD_MATCHES:
        return None, 0

    src_pts = np.float32([kp_query[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp_ref[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

    M, inlier_mask = cv2.estimateAffine2D(
        src_pts, dst_pts,
        method=cv2.RANSAC,
        ransacReprojThreshold=RANSAC_REPROJ_THRESHOLD,
        confidence=0.999,
    )

    if M is None or inlier_mask is None:
        return None, 0

    inliers = int(inlier_mask.sum())
    return M, inliers


def validate_affine(M: np.ndarray, img_h: int, img_w: int) -> tuple[bool, str]:
    """
    Validate an affine transform is geometrically reasonable.
    Returns (is_valid, reason).
    """
    if M is None:
        return False, "null transform"

    # Extract rotation angle from the 2x2 part
    a, b = M[0, 0], M[0, 1]
    c, d = M[1, 0], M[1, 1]

    rotation_rad = math.atan2(c, a)
    rotation_deg = abs(math.degrees(rotation_rad))
    if rotation_deg > MAX_ROTATION_DEG:
        return False, f"rotation {rotation_deg:.1f}° > {MAX_ROTATION_DEG}°"

    # Extract scale
    sx = math.sqrt(a * a + c * c)
    sy = math.sqrt(b * b + d * d)
    if abs(sx - 1.0) > MAX_SCALE_DEVIATION or abs(sy - 1.0) > MAX_SCALE_DEVIATION:
        return False, f"scale ({sx:.2f}, {sy:.2f}) out of range"

    # Check translation
    tx, ty = abs(M[0, 2]), abs(M[1, 2])
    max_tx = img_w * MAX_TRANSLATION_FRAC
    max_ty = img_h * MAX_TRANSLATION_FRAC
    if tx > max_tx or ty > max_ty:
        return False, f"translation ({tx:.0f}, {ty:.0f}) too large"

    return True, "ok"


def affine_to_3x3(M: np.ndarray) -> np.ndarray:
    """Convert 2x3 affine matrix to 3x3 for composition."""
    H = np.eye(3, dtype=np.float64)
    H[:2, :] = M
    return H


def compose_affines(M1: np.ndarray, M2: np.ndarray) -> np.ndarray:
    """Compose two affine transforms: result maps through M1 then M2."""
    H1 = affine_to_3x3(M1)
    H2 = affine_to_3x3(M2)
    return (H2 @ H1)[:2, :]


def find_working_resolution(image_paths: list[Path]) -> tuple[int, int]:
    """Find the most common image resolution to use as working resolution."""
    from collections import Counter
    resolutions = Counter()
    for p in image_paths:
        img = cv2.imread(str(p), cv2.IMREAD_COLOR)
        if img is not None:
            h, w = img.shape[:2]
            resolutions[(h, w)] += 1
    most_common = resolutions.most_common(1)[0][0]
    print(f"  Most common resolution: {most_common[1]}x{most_common[0]} "
          f"({resolutions[most_common]}/{len(image_paths)} images)")
    return most_common


def load_and_normalize(image_paths: list[Path], work_h: int, work_w: int, sift: cv2.SIFT):
    """Load all images, resize to working resolution, extract features."""
    n = len(image_paths)
    print(f"  Loading and normalizing {n} images to {work_w}x{work_h}...")

    images = []  # normalized images
    features = []
    for i, p in enumerate(image_paths):
        img = load_image(p)
        normalized = resize_to_reference(img, work_h, work_w)
        images.append(normalized)
        kp, des = detect_and_compute(sift, normalized)
        features.append((kp, des))
        sys.stdout.write(f"\r  Feature extraction: {i + 1}/{n}")
        sys.stdout.flush()
    print()
    return images, features


def select_reference_image(image_paths: list[Path], features: list):
    """Auto-select the most centered reference image using consecutive affines."""
    n = len(image_paths)

    positions = np.zeros((n, 2))
    for i in range(1, n):
        kp_prev, des_prev = features[i - 1]
        kp_curr, des_curr = features[i]

        good = match_descriptors(des_prev, des_curr)
        M, inliers = estimate_affine(kp_prev, kp_curr, good)

        if M is not None and inliers >= MIN_INLIERS:
            positions[i] = positions[i - 1] + np.array([M[0, 2], M[1, 2]])
        else:
            positions[i] = positions[i - 1]

    centroid = positions.mean(axis=0)
    distances = np.linalg.norm(positions - centroid, axis=1)
    ref_idx = int(np.argmin(distances))

    print(f"  Selected reference: {image_paths[ref_idx].name} (index {ref_idx})")
    return ref_idx


def try_chain_alignment(
    target_idx: int,
    ref_idx: int,
    features: list,
    images: list,
    direct_transforms: dict,
) -> tuple[np.ndarray | None, int, str]:
    """
    Try to align target to reference by chaining through temporal neighbors
    that already have good direct transforms.
    """
    n = len(features)

    # Search for the nearest neighbor with a valid direct transform
    for offset in range(1, min(10, n)):
        for neighbor_idx in [target_idx - offset, target_idx + offset]:
            if neighbor_idx < 0 or neighbor_idx >= n:
                continue
            if neighbor_idx not in direct_transforms:
                continue
            if direct_transforms[neighbor_idx] is None:
                continue

            # Try matching target to this neighbor
            kp_nb, des_nb = features[neighbor_idx]
            kp_tgt, des_tgt = features[target_idx]

            good = match_descriptors(des_nb, des_tgt)
            M_to_nb, inliers = estimate_affine(kp_nb, kp_tgt, good)

            if M_to_nb is None or inliers < MIN_INLIERS:
                continue

            h_tgt, w_tgt = images[target_idx].shape[:2]
            valid, reason = validate_affine(M_to_nb, h_tgt, w_tgt)
            if not valid:
                continue

            # Chain: target -> neighbor -> reference
            M_nb_to_ref = direct_transforms[neighbor_idx]
            M_chained = compose_affines(M_to_nb, M_nb_to_ref)

            # Validate the chained result too
            valid, reason = validate_affine(M_chained, h_tgt, w_tgt)
            if not valid:
                continue

            return M_chained, inliers, f"chained via {neighbor_idx}"

    return None, 0, "no chain found"


def align_images(image_dir: Path, output_dir: Path, transforms_path: Path):
    """Main alignment pipeline."""
    extensions = {".jpg", ".jpeg", ".webp", ".png"}
    image_paths = sorted(
        [p for p in image_dir.iterdir() if p.suffix.lower() in extensions],
        key=lambda p: p.stem,
    )

    if len(image_paths) < 2:
        print("Need at least 2 images.")
        sys.exit(1)

    print(f"Found {len(image_paths)} images")

    sift = cv2.SIFT_create(nfeatures=SIFT_NFEATURES)

    # Step 1: Find working resolution and load/normalize all images
    work_h, work_w = find_working_resolution(image_paths)
    images, features = load_and_normalize(image_paths, work_h, work_w, sift)

    # Step 2: Select reference image
    ref_idx = select_reference_image(image_paths, features)
    ref_img = images[ref_idx]
    ref_kp, ref_des = features[ref_idx]
    ref_h, ref_w = ref_img.shape[:2]

    # Step 3: Compute affine transforms to reference (direct matching)
    print("\nComputing affine transforms to reference...")
    transforms = {}  # index -> 2x3 affine matrix or None
    transform_info = {}  # index -> dict with metadata

    transforms[ref_idx] = np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float64)
    transform_info[ref_idx] = {"inliers": -1, "quality": "reference", "method": "identity"}

    for i, p in enumerate(image_paths):
        if i == ref_idx:
            continue

        kp_i, des_i = features[i]
        good = match_descriptors(ref_des, des_i)
        M, inliers = estimate_affine(ref_kp, kp_i, good)

        if M is not None and inliers >= MIN_INLIERS:
            h_i, w_i = images[i].shape[:2]
            valid, reason = validate_affine(M, h_i, w_i)
            if valid:
                transforms[i] = M
                transform_info[i] = {
                    "inliers": inliers,
                    "quality": "ok",
                    "method": "direct",
                    "matches": len(good),
                }
                print(f"  {p.name}: ok ({inliers} inliers, direct)")
                continue
            else:
                print(f"  {p.name}: rejected direct ({reason})")
        else:
            n_matches = len(good)
            print(f"  {p.name}: direct failed ({inliers} inliers, {n_matches} matches)")

        transforms[i] = None
        transform_info[i] = {"inliers": 0, "quality": "pending", "method": "none"}

    # Step 4: Chain alignment for failed images
    pending = [i for i in range(len(image_paths)) if transform_info[i]["quality"] == "pending"]
    if pending:
        print(f"\nAttempting chain alignment for {len(pending)} images...")
        for i in pending:
            M, inliers, method = try_chain_alignment(i, ref_idx, features, images, transforms)
            if M is not None:
                transforms[i] = M
                transform_info[i] = {
                    "inliers": inliers,
                    "quality": "chained",
                    "method": method,
                }
                print(f"  {image_paths[i].name}: ok ({method}, {inliers} inliers)")
            else:
                transform_info[i]["quality"] = "failed"
                print(f"  {image_paths[i].name}: FAILED (no valid alignment found)")

    # Step 5: Compute output dimensions based on reference image
    # Canvas = reference image dimensions + padding for alignment offsets
    pad_x = int(ref_w * CANVAS_PADDING_FRAC)
    pad_y = int(ref_h * CANVAS_PADDING_FRAC)

    canvas_w = ref_w + 2 * pad_x
    canvas_h = ref_h + 2 * pad_y

    # Scale to output size (long side = OUTPUT_LONG_SIDE)
    if canvas_w >= canvas_h:
        out_w = OUTPUT_LONG_SIDE
        out_h = int(round(canvas_h * OUTPUT_LONG_SIDE / canvas_w))
    else:
        out_h = OUTPUT_LONG_SIDE
        out_w = int(round(canvas_w * OUTPUT_LONG_SIDE / canvas_h))

    scale = out_w / canvas_w

    # Translation to center the reference in the padded canvas
    T_pad = np.array([[1, 0, pad_x], [0, 1, pad_y], [0, 0, 1]], dtype=np.float64)
    S = np.array([[scale, 0, 0], [0, scale, 0], [0, 0, 1]], dtype=np.float64)

    print(f"\nReference image: {ref_w}x{ref_h}")
    print(f"Canvas (with padding): {canvas_w}x{canvas_h}")
    print(f"Output: {out_w}x{out_h}")

    # Step 6: Warp and write images
    print("\nWarping images...")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_images = []

    for i, p in enumerate(image_paths):
        date_str = p.stem.split("_")[0]
        info = transform_info[i]

        entry = {
            "filename": f"{p.stem}.webp",
            "original": p.name,
            "date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}",
            "index": i,
            "is_reference": i == ref_idx,
            "quality": info["quality"],
            "inliers": info["inliers"],
            "method": info["method"],
        }

        M = transforms[i]
        if M is None:
            entry["skipped"] = True
            manifest_images.append(entry)
            print(f"  {p.name}: SKIPPED")
            continue

        # Composite: Scale * T_pad * Affine(3x3)
        H = affine_to_3x3(M)
        composite = S @ T_pad @ H
        warped = cv2.warpPerspective(
            images[i], composite, (out_w, out_h),
            flags=cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0),
        )

        out_path = output_dir / f"{p.stem}.webp"
        cv2.imwrite(str(out_path), warped, [cv2.IMWRITE_WEBP_QUALITY, 90])

        entry["skipped"] = False
        manifest_images.append(entry)
        print(f"  {p.name} -> {out_path.name} [{info['quality']}]")

    # Step 7: Write transforms.json
    manifest = {
        "reference_image": image_paths[ref_idx].name,
        "reference_index": ref_idx,
        "canvas": {"width": out_w, "height": out_h},
        "images": manifest_images,
    }

    transforms_path.parent.mkdir(parents=True, exist_ok=True)
    with open(transforms_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Summary
    qualities = [e["quality"] for e in manifest_images]
    included = len([e for e in manifest_images if not e.get("skipped")])
    skipped = len([e for e in manifest_images if e.get("skipped")])
    print(f"\nDone! {included} images aligned, {skipped} skipped.")
    print(f"Quality: ok={qualities.count('ok')} chained={qualities.count('chained')} "
          f"reference={qualities.count('reference')} failed={qualities.count('failed')}")
    print(f"Transforms written to: {transforms_path}")


if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    image_dir = project_root / "images"
    output_dir = project_root / "public" / "aligned"
    transforms_path = project_root / "public" / "transforms.json"

    if not image_dir.exists():
        print(f"Image directory not found: {image_dir}")
        print("Create an 'images/' directory and place source photos there.")
        sys.exit(1)

    align_images(image_dir, output_dir, transforms_path)
