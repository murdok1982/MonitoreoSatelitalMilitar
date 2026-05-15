import requests
import json
import base64
from typing import Optional


class OllamaAnalyst:
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip('/')
        self.model = model

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def analyze_detection(self, vehicle_count: int, coordinates: list, image_path: Optional[str] = None) -> str:
        """Generate PMESII-PT tactical analysis from detection data."""
        prompt = f"""Eres AEGIS, un analista de inteligencia IMINT de nivel estratégico.

DATOS DE DETECCIÓN:
- Vehículos militares detectados: {vehicle_count}
- Coordenadas de zona (WGS84): {coordinates}
- Umbral de alerta: activado

Genera un informe de inteligencia IMINT con formato NATO en español que incluya:
1. EVALUACIÓN DE AMENAZA (escala 1-5)
2. ANÁLISIS PMESII-PT (solo apartados relevantes)
3. POSIBLES INTENCIONES del actor detectado
4. RECOMENDACIONES INMEDIATAS para el comandante
5. NIVEL DE CONFIANZA (escala NATO A1-F6)

Sé conciso, técnico y militar. Máximo 300 palabras."""

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 500}
        }

        # If we have an image and model supports vision (llava)
        if image_path and 'llava' in self.model.lower():
            try:
                with open(image_path, 'rb') as f:
                    img_b64 = base64.b64encode(f.read()).decode()
                payload["images"] = [img_b64]
            except Exception:
                pass

        try:
            r = requests.post(f"{self.base_url}/api/generate", json=payload, timeout=60)
            if r.status_code == 200:
                return r.json().get('response', 'Análisis no disponible.')
        except Exception as e:
            return f"Ollama no disponible: {e}"
        return "Análisis no disponible."

    def classify_threat_level(self, vehicle_count: int, trend: str) -> dict:
        """Return structured threat classification."""
        if vehicle_count == 0:
            level, color, action = "VERDE", "green", "Sin actividad. Continuar vigilancia rutinaria."
        elif vehicle_count < 5:
            level, color, action = "AMARILLO", "orange", "Actividad detectada. Incrementar frecuencia de barrido."
        elif vehicle_count < 15:
            level, color, action = "NARANJA", "red", "Concentración significativa. Alertar a comandancia."
        else:
            level, color, action = "ROJO", "darkred", "AMENAZA CRÍTICA. Activar protocolo de alerta máxima."

        return {"level": level, "color": color, "action": action, "count": vehicle_count, "trend": trend}
