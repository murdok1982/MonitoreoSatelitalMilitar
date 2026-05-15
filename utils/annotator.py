"""
Image Annotator — AEGIS-IMINT
Draws military-style bounding boxes and threat overlays on satellite images.
"""
import cv2
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import os
import time


@dataclass
class Detection:
    x1: int
    y1: int
    x2: int
    y2: int
    class_name: str
    confidence: float
    threat_color: Tuple[int, int, int] = field(default=(0, 0, 255))  # BGR


class MilitaryAnnotator:
    """
    Annotates satellite images with military-style overlays.
    Color coding: GREEN=low threat, YELLOW=medium, RED=high, WHITE=unknown
    """

    THREAT_COLORS = {
        'tank': (0, 0, 255),               # Red — highest threat
        'armored vehicle': (0, 0, 255),
        'military vehicle': (0, 80, 255),   # Orange-red
        'truck': (0, 165, 255),             # Orange
        'vehicle': (0, 200, 200),           # Yellow
        'car': (0, 255, 200),
        'aircraft': (255, 0, 0),            # Blue — air asset
        'helicopter': (255, 50, 50),
        'ship': (200, 0, 200),              # Magenta — naval
        'boat': (180, 0, 180),
    }
    DEFAULT_COLOR = (200, 200, 200)  # Gray — unknown

    def get_color(self, class_name: str) -> Tuple[int, int, int]:
        """Return the threat colour for a given class name (case-insensitive substring match)."""
        name_lower = class_name.lower()
        for key, color in self.THREAT_COLORS.items():
            if key in name_lower:
                return color
        return self.DEFAULT_COLOR

    def annotate(self, image_path: str, detections: List[Detection],
                 threat_level: str = "VERDE", output_dir: str = 'imagenes') -> str:
        """
        Draw detections on image. Returns path to the annotated output image.

        Parameters
        ----------
        image_path  : path to the source satellite image
        detections  : list of Detection objects to draw
        threat_level: one of VERDE / AMARILLO / NARANJA / ROJO
        output_dir  : directory where the annotated image is saved
        """
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Cannot open image: {image_path}")

        h, w = img.shape[:2]

        # --- Military-style header bar ----------------------------------------
        header_h = 40
        cv2.rectangle(img, (0, 0), (w, header_h), (20, 20, 20), -1)
        level_color = {
            'VERDE':    (0, 200, 0),
            'AMARILLO': (0, 200, 200),
            'NARANJA':  (0, 128, 255),
            'ROJO':     (0, 0, 255),
        }.get(threat_level, (200, 200, 200))
        cv2.putText(
            img,
            f"AEGIS-IMINT | AMENAZA: {threat_level} | VEHÍCULOS: {len(detections)}",
            (10, 28), cv2.FONT_HERSHEY_DUPLEX, 0.65, level_color, 1, cv2.LINE_AA,
        )

        # --- Draw each detection -----------------------------------------------
        for i, det in enumerate(detections):
            # Use detection's own color unless it is the default red sentinel value
            if det.threat_color != (0, 0, 255):
                color = det.threat_color
            else:
                color = self.get_color(det.class_name)

            # Main bounding box
            cv2.rectangle(img, (det.x1, det.y1), (det.x2, det.y2), color, 2)

            # Corner indicators (military style)
            corner_len = max(8, min(20, (det.x2 - det.x1) // 4))
            for cx, cy, dx, dy in [
                (det.x1, det.y1,  1,  1),
                (det.x2, det.y1, -1,  1),
                (det.x1, det.y2,  1, -1),
                (det.x2, det.y2, -1, -1),
            ]:
                cv2.line(img, (cx, cy), (cx + dx * corner_len, cy), color, 3)
                cv2.line(img, (cx, cy), (cx, cy + dy * corner_len), color, 3)

            # Label background + text
            label = f"{i+1}:{det.class_name[:12]} {det.confidence:.0%}"
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            ly = max(det.y1 - 5, lh + 2)
            cv2.rectangle(img, (det.x1, ly - lh - 2), (det.x1 + lw + 4, ly + 2), color, -1)
            cv2.putText(img, label, (det.x1 + 2, ly),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)

        # --- Footer -----------------------------------------------------------
        cv2.rectangle(img, (0, h - 20), (w, h), (20, 20, 20), -1)
        from datetime import datetime, timezone
        ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        cv2.putText(
            img,
            f"CLASIFICADO: RESTRINGIDO | {ts} | Sentinel-2 L1C",
            (10, h - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (150, 150, 150), 1,
        )

        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, f'annotated_{int(time.time())}.png')
        cv2.imwrite(out_path, img)
        return out_path

    def annotate_from_yolo_results(self, image_path: str, yolo_results,
                                   threat_level: str = "VERDE") -> str:
        """
        Convert ultralytics Results objects to Detection list and annotate.

        Parameters
        ----------
        image_path   : path to the source satellite image
        yolo_results : iterable of ultralytics.engine.results.Results
        threat_level : threat level string passed to annotate()
        """
        detections: List[Detection] = []
        for r in yolo_results:
            if r.boxes is None:
                continue
            for box in r.boxes:
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                cls_id = int(box.cls[0])
                cls_name = r.names.get(cls_id, 'unknown')
                conf = float(box.conf[0])
                detections.append(Detection(x1, y1, x2, y2, cls_name, conf))
        return self.annotate(image_path, detections, threat_level)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    import unittest
    import tempfile

    class TestMilitaryAnnotator(unittest.TestCase):

        def setUp(self):
            self.annotator = MilitaryAnnotator()
            # Create a reusable temp directory + dummy image
            self.tmpdir = tempfile.mkdtemp()
            self.img_path = os.path.join(self.tmpdir, 'test_image.png')
            dummy = np.zeros((400, 600, 3), dtype=np.uint8)
            dummy[100:300, 100:500] = (60, 80, 40)   # olive-ish background
            cv2.imwrite(self.img_path, dummy)

        # ------------------------------------------------------------------
        # get_color() tests
        # ------------------------------------------------------------------

        def test_get_color_tank(self):
            """'tank' must map to pure red (0,0,255) in BGR."""
            self.assertEqual(self.annotator.get_color('tank'), (0, 0, 255))

        def test_get_color_armored_vehicle(self):
            self.assertEqual(self.annotator.get_color('Armored Vehicle'), (0, 0, 255))

        def test_get_color_truck(self):
            self.assertEqual(self.annotator.get_color('truck'), (0, 165, 255))

        def test_get_color_aircraft(self):
            self.assertEqual(self.annotator.get_color('aircraft'), (255, 0, 0))

        def test_get_color_ship(self):
            self.assertEqual(self.annotator.get_color('ship'), (200, 0, 200))

        def test_get_color_unknown_returns_default(self):
            """Unknown class names fall back to the DEFAULT_COLOR gray."""
            color = self.annotator.get_color('bicycle')
            self.assertEqual(color, MilitaryAnnotator.DEFAULT_COLOR)

        def test_get_color_case_insensitive(self):
            """Matching must be case-insensitive."""
            self.assertEqual(self.annotator.get_color('TANK'), (0, 0, 255))
            self.assertEqual(self.annotator.get_color('Helicopter'), (255, 50, 50))

        # ------------------------------------------------------------------
        # annotate() — empty detections
        # ------------------------------------------------------------------

        def test_annotate_empty_detections_produces_file(self):
            """annotate() with zero detections must still write an output file."""
            out = self.annotator.annotate(
                self.img_path, [], threat_level='VERDE', output_dir=self.tmpdir
            )
            self.assertTrue(os.path.isfile(out),
                            f"Output file not created: {out}")
            # The file should be a valid image
            result = cv2.imread(out)
            self.assertIsNotNone(result)

        # ------------------------------------------------------------------
        # annotate() — with detections
        # ------------------------------------------------------------------

        def test_annotate_creates_output_file(self):
            """annotate() with detections must create an output file."""
            dets = [
                Detection(50, 50, 150, 120, 'tank', 0.92),
                Detection(200, 100, 320, 200, 'truck', 0.78),
                Detection(400, 150, 550, 280, 'aircraft', 0.65),
            ]
            out = self.annotator.annotate(
                self.img_path, dets, threat_level='ROJO', output_dir=self.tmpdir
            )
            self.assertTrue(os.path.isfile(out))
            img_out = cv2.imread(out)
            self.assertIsNotNone(img_out)
            # Shape must match source (same w×h)
            src = cv2.imread(self.img_path)
            self.assertEqual(img_out.shape, src.shape)

        def test_annotate_nonexistent_image_raises(self):
            """annotate() must raise FileNotFoundError for missing source."""
            with self.assertRaises(FileNotFoundError):
                self.annotator.annotate('/no/such/image.png', [])

        def test_annotate_all_threat_levels(self):
            """annotate() must succeed for all four standard threat levels."""
            for level in ('VERDE', 'AMARILLO', 'NARANJA', 'ROJO'):
                out = self.annotator.annotate(
                    self.img_path, [], threat_level=level, output_dir=self.tmpdir
                )
                self.assertTrue(os.path.isfile(out), f"Failed for level {level}")

        def test_annotate_output_dir_created_if_missing(self):
            """annotate() must create the output directory if it doesn't exist."""
            new_dir = os.path.join(self.tmpdir, 'deep', 'nested', 'dir')
            self.assertFalse(os.path.exists(new_dir))
            out = self.annotator.annotate(
                self.img_path, [], output_dir=new_dir
            )
            self.assertTrue(os.path.isdir(new_dir))
            self.assertTrue(os.path.isfile(out))

    unittest.main(verbosity=2)
