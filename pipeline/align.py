"""
Image alignment pipeline using SIFT + FLANN + constrained homography.

Uses a hybrid approach: tries homography (8 DOF) first for proper perspective
correction, but validates that perspective distortion stays mild. Falls back
to affine (6 DOF) if homography is degenerate. Chain alignment through temporal
neighbors recovers images that fail direct-to-reference matching.

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
MIN_INLIERS = 30
MIN_INLIERS_DIRECT = 40  # stricter for direct-to-reference (low counts = unreliable)

# Geometric validation thresholds
MAX_ROTATION_DEG = 12.0
MAX_SCALE_DEVIATION = 0.25  # allow 0.75x to 1.25x scale
MAX_TRANSLATION_FRAC = 0.30  # max 30% of image dimension shift
MAX_CENTER_DRIFT = 0.15  # warped center must be within 15% of reference center
MAX_PERSPECTIVE = 1e-5  # max absolute value of H[2,0] and H[2,1]
MIN_QUAD_ANGLE_DEG = 30.0  # minimum interior angle after warping corners
MAX_AREA_RATIO = 1.8  # warped area vs original must be within this ratio

# Edge-based fallback parameters
CANNY_LOW = 50
CANNY_HIGH = 150
EDGE_DILATE_KERNEL = 15  # dilate edges to create SIFT detection mask
CLAHE_CLIP_LIMIT = 3.0
CLAHE_GRID_SIZE = 8

# Post-warp quality gate (edge overlap)
QUALITY_EDGE_DILATE = 7  # dilate edges before measuring overlap
MIN_EDGE_OVERLAP = 0.70  # minimum fraction of warped edges that overlap reference edges

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


def detect_and_compute_edges(sift: cv2.SIFT, img: np.ndarray):
    """
    Edge-based feature detection: CLAHE-normalized grayscale with Canny edge mask.
    Focuses SIFT on structural features (building edges, rooflines, riverbank)
    while ignoring seasonal texture/color differences.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # CLAHE normalization to equalize lighting across seasons
    clahe = cv2.createCLAHE(clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=(CLAHE_GRID_SIZE, CLAHE_GRID_SIZE))
    normalized = clahe.apply(gray)

    # Canny edge detection → dilate to create a mask around structural edges
    edges = cv2.Canny(normalized, CANNY_LOW, CANNY_HIGH)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (EDGE_DILATE_KERNEL, EDGE_DILATE_KERNEL))
    mask = cv2.dilate(edges, kernel)

    # SIFT on the CLAHE image, but only detect in edge regions
    kp, des = sift.detectAndCompute(normalized, mask)
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


def _get_match_points(kp_ref, kp_query, good_matches):
    """Extract matched point arrays from keypoints and matches."""
    src_pts = np.float32([kp_query[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp_ref[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    return src_pts, dst_pts


def estimate_homography(kp_ref, kp_query, good_matches):
    """Estimate homography from query to reference using RANSAC."""
    if len(good_matches) < MIN_GOOD_MATCHES:
        return None, 0

    src_pts, dst_pts = _get_match_points(kp_ref, kp_query, good_matches)

    H, inlier_mask = cv2.findHomography(
        src_pts, dst_pts,
        method=cv2.RANSAC,
        ransacReprojThreshold=RANSAC_REPROJ_THRESHOLD,
        confidence=0.999,
    )

    if H is None or inlier_mask is None:
        return None, 0

    inliers = int(inlier_mask.sum())
    return H, inliers


def estimate_affine(kp_ref, kp_query, good_matches):
    """Estimate affine transform from query to reference using RANSAC."""
    if len(good_matches) < MIN_GOOD_MATCHES:
        return None, 0

    src_pts, dst_pts = _get_match_points(kp_ref, kp_query, good_matches)

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


def estimate_transform(kp_ref, kp_query, good_matches, img_h: int, img_w: int):
    """
    Hybrid estimation: try homography first, validate it, fall back to affine.
    Returns (H_3x3, inliers, method_str) or (None, 0, "failed").
    """
    # Try homography first
    H, h_inliers = estimate_homography(kp_ref, kp_query, good_matches)
    if H is not None and h_inliers >= MIN_INLIERS:
        valid, reason = validate_homography(H, img_h, img_w)
        if valid:
            return H, h_inliers, "homography"

    # Fall back to affine
    M, a_inliers = estimate_affine(kp_ref, kp_query, good_matches)
    if M is not None and a_inliers >= MIN_INLIERS:
        H_aff = affine_to_3x3(M)
        valid, reason = validate_homography(H_aff, img_h, img_w)
        if valid:
            return H_aff, a_inliers, "affine"

    return None, 0, "failed"


def validate_homography(H: np.ndarray, img_h: int, img_w: int) -> tuple[bool, str]:
    """
    Validate a 3x3 homography is geometrically reasonable.
    Works for both full homographies and affine-as-3x3.
    Returns (is_valid, reason).
    """
    if H is None:
        return False, "null transform"

    # Normalize so H[2,2] = 1
    if abs(H[2, 2]) < 1e-10:
        return False, "degenerate H[2,2]"
    H = H / H[2, 2]

    # Check perspective components aren't too extreme
    if abs(H[2, 0]) > MAX_PERSPECTIVE or abs(H[2, 1]) > MAX_PERSPECTIVE:
        return False, f"perspective ({H[2,0]:.2e}, {H[2,1]:.2e}) > {MAX_PERSPECTIVE:.0e}"

    # Extract rotation angle from the 2x2 part
    a, b = H[0, 0], H[0, 1]
    c, d = H[1, 0], H[1, 1]

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
    tx, ty = abs(H[0, 2]), abs(H[1, 2])
    max_tx = img_w * MAX_TRANSLATION_FRAC
    max_ty = img_h * MAX_TRANSLATION_FRAC
    if tx > max_tx or ty > max_ty:
        return False, f"translation ({tx:.0f}, {ty:.0f}) too large"

    # Check where the image center maps to — must stay near the reference center
    src_center = np.array([img_w / 2, img_h / 2, 1.0])
    dst_center = H @ src_center
    dst_center = dst_center[:2] / dst_center[2]  # perspective divide
    ref_cx, ref_cy = img_w / 2, img_h / 2
    center_dx = abs(dst_center[0] - ref_cx) / img_w
    center_dy = abs(dst_center[1] - ref_cy) / img_h
    if center_dx > MAX_CENTER_DRIFT or center_dy > MAX_CENTER_DRIFT:
        return False, f"center drift ({center_dx:.2f}, {center_dy:.2f}) > {MAX_CENTER_DRIFT}"

    # Check that warped corners form a reasonable quadrilateral
    corners = np.array([
        [0, 0, 1], [img_w, 0, 1],
        [img_w, img_h, 1], [0, img_h, 1],
    ], dtype=np.float64)
    warped = (H @ corners.T).T
    warped = warped[:, :2] / warped[:, 2:3]  # perspective divide

    # Check interior angles — reject if any angle is too acute (degenerate quad)
    for i in range(4):
        p0 = warped[(i - 1) % 4]
        p1 = warped[i]
        p2 = warped[(i + 1) % 4]
        v1 = p0 - p1
        v2 = p2 - p1
        cos_angle = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-10)
        cos_angle = np.clip(cos_angle, -1, 1)
        angle_deg = math.degrees(math.acos(cos_angle))
        if angle_deg < MIN_QUAD_ANGLE_DEG:
            return False, f"corner angle {angle_deg:.1f}° < {MIN_QUAD_ANGLE_DEG}°"

    # Check area ratio — warped area vs original shouldn't change too much
    original_area = img_w * img_h
    # Shoelace formula for warped quad area
    xs = warped[:, 0]
    ys = warped[:, 1]
    warped_area = 0.5 * abs(
        np.dot(xs, np.roll(ys, -1)) - np.dot(ys, np.roll(xs, -1))
    )
    area_ratio = warped_area / original_area
    if area_ratio > MAX_AREA_RATIO or area_ratio < 1.0 / MAX_AREA_RATIO:
        return False, f"area ratio {area_ratio:.2f} out of range"

    return True, "ok"


def check_edge_overlap(warped: np.ndarray, ref_warped: np.ndarray) -> float:
    """
    Measure structural alignment quality by comparing edge overlap.
    Computes Canny edges on both images, dilates them, and measures
    what fraction of warped image edges fall near reference edges.
    Only considers the non-black (valid) region of the warped image.
    Returns overlap fraction (0.0 = no overlap, 1.0 = perfect).
    """
    # Convert to grayscale
    if len(warped.shape) == 3:
        gray_w = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
    else:
        gray_w = warped
    if len(ref_warped.shape) == 3:
        gray_r = cv2.cvtColor(ref_warped, cv2.COLOR_BGR2GRAY)
    else:
        gray_r = ref_warped

    # Mask of valid (non-black) pixels in the warped image
    valid_mask = gray_w > 5

    # Compute edges
    edges_w = cv2.Canny(gray_w, CANNY_LOW, CANNY_HIGH)
    edges_r = cv2.Canny(gray_r, CANNY_LOW, CANNY_HIGH)

    # Only count edges in valid region
    edges_w = edges_w & valid_mask

    # Dilate reference edges to allow some tolerance
    kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (QUALITY_EDGE_DILATE, QUALITY_EDGE_DILATE)
    )
    edges_r_dilated = cv2.dilate(edges_r, kernel)

    # Count warped edges that overlap with dilated reference edges
    warped_edge_count = int(np.count_nonzero(edges_w))
    if warped_edge_count == 0:
        return 0.0

    overlap_count = int(np.count_nonzero(edges_w & edges_r_dilated))
    return overlap_count / warped_edge_count


def affine_to_3x3(M: np.ndarray) -> np.ndarray:
    """Convert 2x3 affine matrix to 3x3 for composition."""
    H = np.eye(3, dtype=np.float64)
    H[:2, :] = M
    return H


def compose_transforms(H1: np.ndarray, H2: np.ndarray) -> np.ndarray:
    """Compose two 3x3 transforms: result maps through H1 then H2."""
    return H2 @ H1


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
    """Load all images, resize to working resolution, extract features (regular + edge)."""
    n = len(image_paths)
    print(f"  Loading and normalizing {n} images to {work_w}x{work_h}...")

    images = []  # normalized images
    features = []  # (kp, des) regular features
    edge_features = []  # (kp, des) edge-based features
    for i, p in enumerate(image_paths):
        img = load_image(p)
        normalized = resize_to_reference(img, work_h, work_w)
        images.append(normalized)
        kp, des = detect_and_compute(sift, normalized)
        features.append((kp, des))
        ekp, edes = detect_and_compute_edges(sift, normalized)
        edge_features.append((ekp, edes))
        sys.stdout.write(f"\r  Feature extraction: {i + 1}/{n}")
        sys.stdout.flush()
    print()
    return images, features, edge_features


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


def _try_match_to_neighbor(
    target_idx: int,
    neighbor_idx: int,
    feat_tgt,
    feat_nb,
    images: list,
    direct_transforms: dict,
) -> tuple[np.ndarray | None, int]:
    """Try matching target to a neighbor and chain to reference. Returns (H_chained, inliers)."""
    kp_nb, des_nb = feat_nb
    kp_tgt, des_tgt = feat_tgt
    h_tgt, w_tgt = images[target_idx].shape[:2]

    good = match_descriptors(des_nb, des_tgt)
    H_to_nb, inliers, _ = estimate_transform(kp_nb, kp_tgt, good, h_tgt, w_tgt)

    if H_to_nb is None or inliers < MIN_INLIERS:
        return None, 0

    H_nb_to_ref = direct_transforms[neighbor_idx]
    H_chained = compose_transforms(H_to_nb, H_nb_to_ref)

    valid, reason = validate_homography(H_chained, h_tgt, w_tgt)
    if not valid:
        return None, 0

    return H_chained, inliers


def try_chain_alignment(
    target_idx: int,
    ref_idx: int,
    features: list,
    edge_features: list,
    images: list,
    direct_transforms: dict,
) -> tuple[np.ndarray | None, int, str]:
    """
    Try to align target to reference by chaining through temporal neighbors.
    Tries regular features first, then edge features as fallback.
    """
    n = len(features)

    for offset in range(1, min(10, n)):
        for neighbor_idx in [target_idx - offset, target_idx + offset]:
            if neighbor_idx < 0 or neighbor_idx >= n:
                continue
            if neighbor_idx not in direct_transforms:
                continue
            if direct_transforms[neighbor_idx] is None:
                continue

            # Try regular features
            H, inliers = _try_match_to_neighbor(
                target_idx, neighbor_idx,
                features[target_idx], features[neighbor_idx],
                images, direct_transforms,
            )
            if H is not None:
                return H, inliers, f"chained via {neighbor_idx}"

            # Try edge features as fallback
            H, inliers = _try_match_to_neighbor(
                target_idx, neighbor_idx,
                edge_features[target_idx], edge_features[neighbor_idx],
                images, direct_transforms,
            )
            if H is not None:
                return H, inliers, f"chained-edge via {neighbor_idx}"

    return None, 0, "no chain found"


def align_images(image_dir: Path, output_dir: Path, transforms_path: Path, quality_threshold: float = MIN_EDGE_OVERLAP):
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
    images, features, edge_features = load_and_normalize(image_paths, work_h, work_w, sift)

    # Step 2: Select reference image
    ref_idx = select_reference_image(image_paths, features)
    ref_img = images[ref_idx]
    ref_kp, ref_des = features[ref_idx]
    ref_ekp, ref_edes = edge_features[ref_idx]
    ref_h, ref_w = ref_img.shape[:2]

    # Step 3: Compute transforms to reference (hybrid: homography → affine, edge fallback)
    print("\nComputing transforms to reference...")
    transforms = {}  # index -> 3x3 matrix or None
    transform_info = {}  # index -> dict with metadata

    transforms[ref_idx] = np.eye(3, dtype=np.float64)
    transform_info[ref_idx] = {"inliers": -1, "quality": "reference", "method": "identity"}

    for i, p in enumerate(image_paths):
        if i == ref_idx:
            continue

        h_i, w_i = images[i].shape[:2]

        # Try regular features first
        kp_i, des_i = features[i]
        good = match_descriptors(ref_des, des_i)
        H, inliers, method = estimate_transform(ref_kp, kp_i, good, h_i, w_i)

        if H is not None and inliers >= MIN_INLIERS_DIRECT:
            transforms[i] = H
            transform_info[i] = {
                "inliers": inliers,
                "quality": "ok",
                "method": f"direct-{method}",
                "matches": len(good),
            }
            print(f"  {p.name}: ok ({inliers} inliers, {method})")
            continue

        # Try edge features as fallback for direct matching
        ekp_i, edes_i = edge_features[i]
        egood = match_descriptors(ref_edes, edes_i)
        eH, einliers, emethod = estimate_transform(ref_ekp, ekp_i, egood, h_i, w_i)

        if eH is not None and einliers >= MIN_INLIERS_DIRECT:
            transforms[i] = eH
            transform_info[i] = {
                "inliers": einliers,
                "quality": "ok",
                "method": f"direct-edge-{emethod}",
                "matches": len(egood),
            }
            print(f"  {p.name}: ok ({einliers} inliers, edge-{emethod})")
            continue

        n_matches = len(good)
        en_matches = len(egood)
        print(f"  {p.name}: direct failed (reg:{inliers}/{n_matches}, edge:{einliers}/{en_matches})")

        transforms[i] = None
        transform_info[i] = {"inliers": 0, "quality": "pending", "method": "none"}

    # Step 4: Chain alignment for failed images (also uses edge fallback)
    pending = [i for i in range(len(image_paths)) if transform_info[i]["quality"] == "pending"]
    if pending:
        print(f"\nAttempting chain alignment for {len(pending)} images...")
        for i in pending:
            M, inliers, method = try_chain_alignment(
                i, ref_idx, features, edge_features, images, transforms,
            )
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

    # Step 6: Warp and write images, with edge-overlap quality gate
    print("\nWarping images...")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_images = []

    # Warp reference image first for quality comparison
    ref_composite = S @ T_pad @ transforms[ref_idx]
    ref_warped = cv2.warpPerspective(
        images[ref_idx], ref_composite, (out_w, out_h),
        flags=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0),
    )

    quality_rejected = 0
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
            print(f"  {p.name}: SKIPPED (no transform)")
            continue

        # Composite: Scale * T_pad * Transform
        H = M  # already 3x3
        composite = S @ T_pad @ H
        warped = cv2.warpPerspective(
            images[i], composite, (out_w, out_h),
            flags=cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0),
        )

        # Quality gate: check edge overlap with reference (skip for reference itself)
        if i != ref_idx:
            overlap = check_edge_overlap(warped, ref_warped)
            entry["edge_overlap"] = round(overlap, 3)
            if overlap < quality_threshold:
                entry["skipped"] = True
                entry["quality"] = "quality-rejected"
                manifest_images.append(entry)
                quality_rejected += 1
                print(f"  {p.name}: SKIPPED (edge overlap {overlap:.1%} < {quality_threshold:.0%})")
                continue

        out_path = output_dir / f"{p.stem}.webp"
        cv2.imwrite(str(out_path), warped, [cv2.IMWRITE_WEBP_QUALITY, 90])

        entry["skipped"] = False
        manifest_images.append(entry)
        overlap_str = f", overlap {entry.get('edge_overlap', 1.0):.0%}" if i != ref_idx else ""
        print(f"  {p.name} -> {out_path.name} [{info['quality']}{overlap_str}]")

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
          f"reference={qualities.count('reference')} failed={qualities.count('failed')} "
          f"quality-rejected={quality_rejected}")
    print(f"Transforms written to: {transforms_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Align images to a reference frame.")
    parser.add_argument(
        "--quality-threshold", type=float, default=MIN_EDGE_OVERLAP,
        help=f"Min edge-overlap score to keep an image (0.0–1.0, default {MIN_EDGE_OVERLAP})",
    )
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    image_dir = project_root / "images"
    output_dir = project_root / "public" / "aligned"
    transforms_path = project_root / "public" / "transforms.json"

    if not image_dir.exists():
        print(f"Image directory not found: {image_dir}")
        print("Create an 'images/' directory and place source photos there.")
        sys.exit(1)

    align_images(image_dir, output_dir, transforms_path, quality_threshold=args.quality_threshold)
