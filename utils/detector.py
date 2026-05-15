"""
Vehicle Detector — AEGIS-IMINT
Runs YOLO inference on satellite imagery to detect military vehicles.

Extended: detectar_vehiculos() accepts an optional `annotate` flag.
When True, a MilitaryAnnotator overlay is generated and the annotated
image path is returned as a third element of the return tuple.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional imports — gracefully degrade if ultralytics / annotator unavailable
# ---------------------------------------------------------------------------
try:
    from ultralytics import YOLO
    _YOLO_AVAILABLE = True
except ImportError:
    _YOLO_AVAILABLE = False
    logger.warning("ultralytics not installed — YOLO detection disabled")

try:
    from utils.annotator import MilitaryAnnotator, Detection  # package context
except ImportError:
    try:
        from annotator import MilitaryAnnotator, Detection    # standalone / test context
    except ImportError:
        MilitaryAnnotator = None  # type: ignore[assignment,misc]
        Detection = None          # type: ignore[assignment]
        logger.warning("annotator module not found — annotation disabled")


# ---------------------------------------------------------------------------
# Threat level determination
# ---------------------------------------------------------------------------

_THREAT_THRESHOLDS = {
    'ROJO':     5,   # ≥5 vehicles → critical
    'NARANJA':  3,   # ≥3 vehicles → high
    'AMARILLO': 1,   # ≥1 vehicle  → medium
    'VERDE':    0,   # no vehicles → clear
}

_HIGH_THREAT_CLASSES = {'tank', 'armored vehicle', 'military vehicle'}


def calcular_nivel_amenaza(detecciones: list, n_vehicles: int) -> str:
    """
    Derive a threat level string from detection count and class mix.
    Returns one of: VERDE / AMARILLO / NARANJA / ROJO
    """
    if n_vehicles == 0:
        return 'VERDE'

    names_lower = {d.get('clase', '').lower() for d in detecciones}
    if names_lower & _HIGH_THREAT_CLASSES or n_vehicles >= _THREAT_THRESHOLDS['ROJO']:
        return 'ROJO'
    if n_vehicles >= _THREAT_THRESHOLDS['NARANJA']:
        return 'NARANJA'
    return 'AMARILLO'


# ---------------------------------------------------------------------------
# Core detection function
# ---------------------------------------------------------------------------

def detectar_vehiculos(
    imagen_path: str,
    modelo_path: str = 'yolov8n.pt',
    conf_threshold: float = 0.35,
    output_dir: str = 'imagenes',
    annotate: bool = True,
) -> Tuple[List[dict], str, Optional[str]]:
    """
    Run YOLO vehicle detection on *imagen_path*.

    Parameters
    ----------
    imagen_path    : Path to the satellite image to analyse.
    modelo_path    : Path (or Ultralytics hub name) of the YOLO model weights.
    conf_threshold : Minimum confidence to retain a detection.
    output_dir     : Directory for saving result images.
    annotate       : When True, produce a military-annotated overlay image and
                     return its path as the third element of the return tuple.

    Returns
    -------
    detecciones    : List of dicts with keys {clase, confianza, bbox}.
    nivel_amenaza  : Threat level string (VERDE/AMARILLO/NARANJA/ROJO).
    annotated_path : Path to the annotated image, or None when annotate=False
                     or annotation is unavailable.
    """
    if not os.path.exists(imagen_path):
        raise FileNotFoundError(f"Image not found: {imagen_path}")

    # ------------------------------------------------------------------
    # YOLO inference
    # ------------------------------------------------------------------
    if not _YOLO_AVAILABLE:
        logger.error("YOLO unavailable — returning empty detections")
        return [], 'VERDE', None

    try:
        model = YOLO(modelo_path)
    except Exception as exc:
        logger.error("Failed to load YOLO model '%s': %s", modelo_path, exc)
        return [], 'VERDE', None

    try:
        results = model(imagen_path, conf=conf_threshold, verbose=False)
    except Exception as exc:
        logger.error("YOLO inference failed: %s", exc)
        return [], 'VERDE', None

    # ------------------------------------------------------------------
    # Parse results into a standard list of dicts
    # ------------------------------------------------------------------
    detecciones: List[dict] = []
    for r in results:
        if r.boxes is None:
            continue
        for box in r.boxes:
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
            cls_id = int(box.cls[0])
            cls_name = r.names.get(cls_id, 'unknown')
            conf = float(box.conf[0])
            detecciones.append({
                'clase': cls_name,
                'confianza': conf,
                'bbox': [x1, y1, x2, y2],
            })

    nivel_amenaza = calcular_nivel_amenaza(detecciones, len(detecciones))
    logger.info("detectar_vehiculos: %d detections, nivel=%s",
                len(detecciones), nivel_amenaza)

    # ------------------------------------------------------------------
    # Optional annotation
    # ------------------------------------------------------------------
    annotated_path: Optional[str] = None
    if annotate and MilitaryAnnotator is not None:
        try:
            annotated_path = MilitaryAnnotator().annotate_from_yolo_results(
                imagen_path, results, threat_level=nivel_amenaza
            )
            logger.info("Annotated image saved: %s", annotated_path)
        except Exception as exc:
            logger.warning("Annotation failed (non-fatal): %s", exc)

    return detecciones, nivel_amenaza, annotated_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    import unittest
    import tempfile

    class TestDetectorModule(unittest.TestCase):

        def test_calcular_nivel_amenaza_no_vehicles(self):
            self.assertEqual(calcular_nivel_amenaza([], 0), 'VERDE')

        def test_calcular_nivel_amenaza_one_vehicle(self):
            self.assertEqual(
                calcular_nivel_amenaza([{'clase': 'car'}], 1), 'AMARILLO'
            )

        def test_calcular_nivel_amenaza_high_threat_class(self):
            result = calcular_nivel_amenaza([{'clase': 'tank'}], 1)
            self.assertEqual(result, 'ROJO')

        def test_calcular_nivel_amenaza_many_vehicles(self):
            dets = [{'clase': 'truck'}] * 5
            result = calcular_nivel_amenaza(dets, 5)
            self.assertEqual(result, 'ROJO')

        def test_detectar_vehiculos_missing_file_raises(self):
            with self.assertRaises(FileNotFoundError):
                detectar_vehiculos('/no/such/image.png')

        def test_detectar_vehiculos_returns_three_tuple(self):
            """When YOLO is unavailable the function still returns a 3-tuple."""
            if _YOLO_AVAILABLE:
                self.skipTest("YOLO is available; skipping degraded-path test")
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
                tmp = f.name
            try:
                dummy = np.zeros((100, 100, 3), dtype=np.uint8)
                cv2.imwrite(tmp, dummy)
                result = detectar_vehiculos(tmp)
                self.assertIsInstance(result, tuple)
                self.assertEqual(len(result), 3)
                detecciones, nivel, ann_path = result
                self.assertIsInstance(detecciones, list)
                self.assertIsInstance(nivel, str)
            finally:
                os.unlink(tmp)

    unittest.main(verbosity=2)
