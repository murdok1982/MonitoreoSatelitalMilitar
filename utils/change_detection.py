"""
Change Detection Module — AEGIS-IMINT
Compares consecutive Sentinel-2 images to detect new activity.
"""
import cv2
import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple, List
import os
import sqlite3


@dataclass
class ChangeReport:
    zones_new_activity: int      # pixel regions with new detections
    zones_disappeared: int       # objects gone
    change_percentage: float     # % of image that changed
    change_image_path: str       # path to annotated diff image
    summary: str                 # human-readable summary


class ChangeDetector:
    def __init__(self, threshold: float = 0.08, min_area: int = 100):
        """
        threshold: fraction of pixel intensity change to count as significant
        min_area: minimum contour area (pixels) to count as a change region
        """
        self.threshold = threshold
        self.min_area = min_area

    def load_image(self, path: str) -> Optional[np.ndarray]:
        """Load image from path, return as grayscale float32."""
        if not path or not os.path.exists(path):
            return None
        img = cv2.imread(path)
        if img is None:
            return None
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0

    def compare(self, img_before: np.ndarray, img_after: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Return (diff_mask, diff).
        diff_mask: binary mask of changed regions
        diff: absolute difference array (float32)
        """
        # Resize to same size
        h = min(img_before.shape[0], img_after.shape[0])
        w = min(img_before.shape[1], img_after.shape[1])
        b = cv2.resize(img_before, (w, h))
        a = cv2.resize(img_after, (w, h))

        # Absolute difference
        diff = np.abs(a - b)

        # Threshold
        mask = (diff > self.threshold).astype(np.uint8) * 255

        # Morphological cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        return mask, diff

    def analyze(self, path_before: str, path_after: str, output_dir: str = 'imagenes') -> Optional[ChangeReport]:
        """Full change detection pipeline. Returns ChangeReport or None if images can't be loaded."""
        img_before = self.load_image(path_before)
        img_after = self.load_image(path_after)

        if img_before is None or img_after is None:
            return None

        mask, diff = self.compare(img_before, img_after)

        # Find contours of change regions
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        significant = [c for c in contours if cv2.contourArea(c) >= self.min_area]

        change_pct = float(np.sum(mask > 0)) / mask.size * 100

        # Create visualization: overlay on after image
        after_bgr = cv2.imread(path_after)
        if after_bgr is None:
            after_bgr_vis = np.zeros((mask.shape[0], mask.shape[1], 3), dtype=np.uint8)
        else:
            after_bgr_vis = cv2.resize(after_bgr, (mask.shape[1], mask.shape[0]))

        # Draw change regions in red
        overlay = after_bgr_vis.copy()
        cv2.drawContours(overlay, significant, -1, (0, 0, 255), 2)

        # Color the diff areas semi-transparent red
        red_mask = np.zeros_like(overlay)
        red_mask[mask > 0] = (0, 0, 200)
        vis = cv2.addWeighted(overlay, 0.7, red_mask, 0.3, 0)

        # Add text info
        cv2.putText(vis, f"CAMBIOS: {len(significant)} zonas | {change_pct:.1f}%",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        import time
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, f'change_{int(time.time())}.png')
        cv2.imwrite(out_path, vis)

        # Classify as new activity or disappeared based on intensity direction
        diff_colored = cv2.resize(diff, (mask.shape[1], mask.shape[0]))
        new_activity = sum(1 for c in significant if _mean_intensity_in_contour(diff_colored, c) > 0)
        disappeared = len(significant) - new_activity

        summary = _build_summary(len(significant), change_pct, new_activity, disappeared)

        return ChangeReport(
            zones_new_activity=new_activity,
            zones_disappeared=disappeared,
            change_percentage=change_pct,
            change_image_path=out_path,
            summary=summary,
        )


def _mean_intensity_in_contour(diff: np.ndarray, contour) -> float:
    mask = np.zeros(diff.shape[:2], dtype=np.uint8)
    cv2.drawContours(mask, [contour], -1, 255, -1)
    return float(np.mean(diff[mask > 0])) if np.any(mask > 0) else 0.0


def _build_summary(n_zones: int, pct: float, new: int, gone: int) -> str:
    if n_zones == 0:
        return "Sin cambios significativos desde la última imagen."
    level = "MÍNIMO" if pct < 2 else "MODERADO" if pct < 10 else "SIGNIFICATIVO" if pct < 25 else "CRÍTICO"
    return (f"Nivel de cambio {level} ({pct:.1f}% del área). "
            f"{new} zonas con nueva actividad detectada, {gone} zonas con actividad cesada.")


def get_previous_image(db_path: str, bbox: list) -> Optional[str]:
    """Get the most recent previous image path for the same approximate bbox from DB."""
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        # Match bbox within ~0.1 degree tolerance
        tol = 0.1
        c.execute("""SELECT imagen_path FROM detecciones
                     WHERE lon_min BETWEEN ? AND ? AND lat_min BETWEEN ? AND ?
                     AND imagen_path IS NOT NULL AND imagen_path != ''
                     ORDER BY timestamp DESC LIMIT 1""",
                  (bbox[0]-tol, bbox[0]+tol, bbox[1]-tol, bbox[1]+tol))
        row = c.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    import unittest
    import tempfile

    class TestChangeDetector(unittest.TestCase):

        def setUp(self):
            self.detector = ChangeDetector(threshold=0.08, min_area=10)

        def test_load_nonexistent_returns_none(self):
            """load_image() on a missing file must return None."""
            result = self.detector.load_image("nonexistent.jpg")
            self.assertIsNone(result)

        def test_load_empty_path_returns_none(self):
            """load_image() on an empty string must return None."""
            result = self.detector.load_image("")
            self.assertIsNone(result)

        def test_compare_identical_images_near_zero_change(self):
            """Comparing an image with itself should yield near-zero change percentage."""
            # Create a synthetic grayscale float32 array
            img = np.random.rand(100, 100).astype(np.float32)
            mask, diff = self.detector.compare(img, img)
            change_pct = float(np.sum(mask > 0)) / mask.size * 100
            # Identical images → 0% change (within floating-point rounding)
            self.assertAlmostEqual(change_pct, 0.0, places=3)

        def test_compare_different_images_high_change(self):
            """Comparing all-zeros vs all-ones should yield very high change percentage."""
            img_black = np.zeros((100, 100), dtype=np.float32)
            img_white = np.ones((100, 100), dtype=np.float32)
            # Use a low threshold so all pixels register as changed
            detector = ChangeDetector(threshold=0.05, min_area=1)
            mask, diff = detector.compare(img_black, img_white)
            change_pct = float(np.sum(mask > 0)) / mask.size * 100
            # After morphological ops most pixels should still be flagged
            self.assertGreater(change_pct, 80.0)

        def test_build_summary_no_changes(self):
            summary = _build_summary(0, 0.0, 0, 0)
            self.assertIn("Sin cambios", summary)

        def test_build_summary_critical(self):
            summary = _build_summary(10, 30.0, 7, 3)
            self.assertIn("CRÍTICO", summary)
            self.assertIn("7 zonas con nueva actividad", summary)
            self.assertIn("3 zonas con actividad cesada", summary)

        def test_analyze_missing_paths_returns_none(self):
            result = self.detector.analyze("no_before.png", "no_after.png", output_dir='/tmp')
            self.assertIsNone(result)

        def test_analyze_creates_output_file(self):
            """End-to-end analyze() with real temp images."""
            with tempfile.TemporaryDirectory() as tmpdir:
                # Write two slightly different images
                before = np.zeros((200, 200, 3), dtype=np.uint8)
                after = np.zeros((200, 200, 3), dtype=np.uint8)
                after[50:100, 50:100] = 255  # large bright block

                path_before = os.path.join(tmpdir, 'before.png')
                path_after = os.path.join(tmpdir, 'after.png')
                cv2.imwrite(path_before, before)
                cv2.imwrite(path_after, after)

                out_dir = os.path.join(tmpdir, 'output')
                report = self.detector.analyze(path_before, path_after, output_dir=out_dir)

                self.assertIsNotNone(report)
                self.assertTrue(os.path.exists(report.change_image_path))
                self.assertGreater(report.change_percentage, 0.0)

    unittest.main(verbosity=2)
