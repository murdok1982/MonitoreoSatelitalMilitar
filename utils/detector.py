import os
from typing import Tuple, List
from config import YOLO_MODEL_PATH, CONFIDENCE_THRESHOLD

# Military vehicle class names (for models trained on xView/DOTA)
MILITARY_CLASSES = {
    'vehicle', 'military vehicle', 'tank', 'armored vehicle', 'truck',
    'car', 'van', 'bus', 'helicopter', 'aircraft', 'ship', 'boat',
    'fixed-wing aircraft', 'small aircraft', 'cargo truck', 'engineering vehicle',
    'ground track vehicle',
}

_model = None


def _load_model():
    global _model
    if _model is None:
        if not os.path.exists(YOLO_MODEL_PATH):
            raise FileNotFoundError(
                f"Modelo no encontrado: {YOLO_MODEL_PATH}\n"
                "Descarga un modelo pre-entrenado de xView o DOTA y colócalo en /modelos/"
            )
        from ultralytics import YOLO
        _model = YOLO(YOLO_MODEL_PATH)
    return _model


def detectar_vehiculos(imagen_path: str) -> Tuple[int, List[str]]:
    """
    Run YOLO inference. Returns (count, class_names_list).
    Filters for military-relevant classes only; falls back to all
    detected classes when the model uses a general-purpose vocabulary.
    """
    model = _load_model()
    results = model.predict(imagen_path, conf=CONFIDENCE_THRESHOLD, verbose=False)

    clases_detectadas = []
    for r in results:
        if r.boxes is not None and r.names:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                cls_name = r.names.get(cls_id, 'unknown').lower()
                clases_detectadas.append(cls_name)

    # Filter to military-relevant classes; keep all if none match (general model)
    militares = [c for c in clases_detectadas if any(m in c for m in MILITARY_CLASSES)]
    count = len(militares) if militares else len(clases_detectadas)
    return count, clases_detectadas


def model_available() -> bool:
    return os.path.exists(YOLO_MODEL_PATH)
