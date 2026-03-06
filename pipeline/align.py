"""
Image alignment pipeline using SIFT + FLANN + RANSAC homography.

Aligns all source images to an auto-selected reference frame,
expands canvas to preserve all pixels (no crop), and outputs
uniformly sized images + transforms.json.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np

# --- Configuration ---
MAX_LONG_SIDE = 1500
SIFT_NFEATURES = 4000
FLANN_TREES = 5
FLANN_CHECKS = 100
LOWE_RATIO = 0.7
RANSAC_REPROJ_THRESHOLD = 5.0
MIN_GOOD_MATCHES = 10


def load_image(path: Path) -> np.ndarray:
    """Load image from path, handling various formats."""
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Could not load image: {path}")
    return img


def detect_and_compute(sift: cv2.SIFT, img: np.ndarray):
    """Detect keypoints and compute descriptors."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    kp, des = sift.detectAndCompute(gray, None)
    return kp, des


def match_descriptors(des_ref: np.ndarray, des_query: np.ndarray):
    """Match descriptors using FLANN with Lowe's ratio test."""
    index_params = dict(algorithm=1, trees=FLANN_TREES)  # FLANN_INDEX_KDTREE = 1
    search_params = dict(checks=FLANN_CHECKS)
    flann = cv2.FlannBasedMatcher(index_params, search_params)

    matches = flann.knnMatch(des_query, des_ref, k=2)

    good = []
    for m, n in matches:
        if m.distance < LOWE_RATIO * n.distance:
            good.append(m)
    return good


def find_homography(kp_ref, kp_query, good_matches):
    """Find homography from query to reference using RANSAC."""
    if len(good_matches) < MIN_GOOD_MATCHES:
        return None, 0

    src_pts = np.float32([kp_query[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp_ref[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

    H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, RANSAC_REPROJ_THRESHOLD)
    inliers = int(mask.sum()) if mask is not None else 0
    return H, inliers


def compute_warped_bounds(H: np.ndarray, h: int, w: int):
    """Compute the bounding box of the warped image corners."""
    corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
    warped_corners = cv2.perspectiveTransform(corners, H)
    return warped_corners.reshape(-1, 2)


def select_reference_image(image_paths: list[Path], sift: cv2.SIFT) -> int:
    """
    Auto-select the most centered reference image.
    Strategy: pick the image that minimizes the sum of homography translation
    components to its neighbors (i.e., the image closest to the "average" position).
    We approximate by computing pairwise homographies between consecutive images
    and finding the image with smallest cumulative displacement.
    """
    n = len(image_paths)
    if n <= 2:
        return n // 2

    # Compute consecutive homographies to estimate relative positions
    positions = np.zeros((n, 2))  # cumulative x, y translation
    print(f"  Selecting reference image from {n} candidates...")

    images = []
    features = []
    for i, p in enumerate(image_paths):
        img = load_image(p)
        images.append(img)
        kp, des = detect_and_compute(sift, img)
        features.append((kp, des))
        sys.stdout.write(f"\r  Feature extraction: {i + 1}/{n}")
        sys.stdout.flush()
    print()

    # Accumulate positions from consecutive pairs
    for i in range(1, n):
        kp_prev, des_prev = features[i - 1]
        kp_curr, des_curr = features[i]

        if des_prev is None or des_curr is None:
            positions[i] = positions[i - 1]
            continue

        good = match_descriptors(des_prev, des_curr)
        H, inliers = find_homography(kp_prev, kp_curr, good)

        if H is not None and inliers >= MIN_GOOD_MATCHES:
            # Translation component of homography
            tx, ty = H[0, 2], H[1, 2]
            positions[i] = positions[i - 1] + np.array([tx, ty])
        else:
            positions[i] = positions[i - 1]

    # Find the image closest to the centroid of all positions
    centroid = positions.mean(axis=0)
    distances = np.linalg.norm(positions - centroid, axis=1)
    ref_idx = int(np.argmin(distances))

    print(f"  Selected reference image: {image_paths[ref_idx].name} (index {ref_idx})")
    return ref_idx, images, features


def align_images(
    image_dir: Path,
    output_dir: Path,
    transforms_path: Path,
):
    """Main alignment pipeline."""
    # Discover images
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

    # Step 1: Select reference image
    ref_idx, images, features = select_reference_image(image_paths, sift)
    ref_img = images[ref_idx]
    ref_kp, ref_des = features[ref_idx]
    ref_h, ref_w = ref_img.shape[:2]

    # Step 2: Compute homographies to reference
    print("\nComputing homographies to reference...")
    homographies = {}
    for i, p in enumerate(image_paths):
        if i == ref_idx:
            homographies[i] = {
                "H": np.eye(3),
                "inliers": -1,
                "quality": "reference",
            }
            continue

        kp_i, des_i = features[i]
        if des_i is None:
            homographies[i] = {"H": None, "inliers": 0, "quality": "failed"}
            print(f"  {p.name}: FAILED (no descriptors)")
            continue

        good = match_descriptors(ref_des, des_i)
        H, inliers = find_homography(ref_kp, kp_i, good)

        quality = "ok" if inliers >= 30 else "low" if inliers >= MIN_GOOD_MATCHES else "failed"
        homographies[i] = {"H": H, "inliers": inliers, "quality": quality}
        print(f"  {p.name}: {quality} ({inliers} inliers, {len(good)} good matches)")

    # Step 3: Compute global canvas bounds (only from "ok" and "reference" quality)
    print("\nComputing canvas bounds (using only good-quality homographies)...")
    all_corners = [np.float32([[0, 0], [ref_w, 0], [ref_w, ref_h], [0, ref_h]])]

    # Max allowed expansion: 2x the reference image dimensions in any direction
    max_extent = max(ref_w, ref_h) * 2

    for i in range(len(image_paths)):
        data = homographies[i]
        if data["H"] is None or data["quality"] not in ("ok", "reference"):
            continue
        h_i, w_i = images[i].shape[:2]
        corners = compute_warped_bounds(data["H"], h_i, w_i)
        # Sanity check: skip if any corner is wildly out of range
        if np.any(np.abs(corners) > max_extent):
            print(f"  Skipping {image_paths[i].name} from bounds (extreme warp)")
            homographies[i]["quality"] = "low"
            continue
        all_corners.append(corners)

    all_corners = np.vstack(all_corners)
    x_min, y_min = all_corners.min(axis=0)
    x_max, y_max = all_corners.max(axis=0)

    # Translation to shift everything into positive coordinates
    tx = -x_min
    ty = -y_min
    T = np.array([[1, 0, tx], [0, 1, ty], [0, 0, 1]], dtype=np.float64)

    canvas_w = int(np.ceil(x_max - x_min))
    canvas_h = int(np.ceil(y_max - y_min))
    print(f"Canvas size: {canvas_w} x {canvas_h}")

    # Step 4: Compute output dimensions (1500px on longer side, preserving aspect)
    if canvas_w >= canvas_h:
        out_w = MAX_LONG_SIDE
        out_h = int(round(canvas_h * MAX_LONG_SIDE / canvas_w))
    else:
        out_h = MAX_LONG_SIDE
        out_w = int(round(canvas_w * MAX_LONG_SIDE / canvas_h))

    scale = out_w / canvas_w
    S = np.array([[scale, 0, 0], [0, scale, 0], [0, 0, 1]], dtype=np.float64)

    print(f"Output size: {out_w} x {out_h}")

    # Step 5: Warp and write images
    print("\nWarping images...")
    output_dir.mkdir(parents=True, exist_ok=True)
    transforms = []

    for i, p in enumerate(image_paths):
        data = homographies[i]
        # Extract date from filename
        date_str = p.stem.split("_")[0]

        entry = {
            "filename": f"{p.stem}.webp",
            "original": p.name,
            "date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}",
            "index": i,
            "is_reference": i == ref_idx,
            "quality": data["quality"],
            "inliers": data["inliers"],
        }

        if data["H"] is None:
            entry["H"] = None
            entry["skipped"] = True
            transforms.append(entry)
            print(f"  {p.name}: SKIPPED (alignment failed)")
            continue

        # Composite transform: Scale * Translate * Homography
        composite = S @ T @ data["H"]
        warped = cv2.warpPerspective(images[i], composite, (out_w, out_h))

        out_path = output_dir / f"{p.stem}.webp"
        cv2.imwrite(str(out_path), warped, [cv2.IMWRITE_WEBP_QUALITY, 85])

        entry["H"] = data["H"].tolist()
        entry["skipped"] = False
        transforms.append(entry)
        print(f"  {p.name} -> {out_path.name}")

    # Step 6: Write transforms.json
    manifest = {
        "reference_image": image_paths[ref_idx].name,
        "reference_index": ref_idx,
        "canvas": {"width": out_w, "height": out_h},
        "scale_factor": scale,
        "translation": [float(tx), float(ty)],
        "images": transforms,
    }

    transforms_path.parent.mkdir(parents=True, exist_ok=True)
    with open(transforms_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nDone! {len([t for t in transforms if not t.get('skipped')])} images aligned.")
    print(f"Transforms written to: {transforms_path}")

    # Summary
    qualities = [t["quality"] for t in transforms]
    print(f"\nQuality summary:")
    print(f"  OK: {qualities.count('ok')}")
    print(f"  Low: {qualities.count('low')}")
    print(f"  Failed: {qualities.count('failed')}")
    print(f"  Reference: {qualities.count('reference')}")


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
