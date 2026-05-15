"""
AEGIS-IMINT REST API — FastAPI C2 Integration Layer
Provides programmatic access for external C2 systems.
Authentication: API Key via X-API-Key header.
"""
from fastapi import FastAPI, HTTPException, Security, BackgroundTasks, Depends
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
import os
import sys
import uuid

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.middleware import RateLimitMiddleware

# ---------------------------------------------------------------------------
# Lazy imports — these modules may not exist in the test environment.
# We provide lightweight stubs so the module-level code (app creation, model
# definitions, route registration) always succeeds.  The stubs are replaced by
# the real implementations if the modules are present on sys.path.
# ---------------------------------------------------------------------------
try:
    from config import DB_PATH, SENSIBILIDAD_ALERTA, OLLAMA_BASE_URL, OLLAMA_MODEL  # type: ignore
except ImportError:
    DB_PATH = os.getenv("AEGIS_DB_PATH", "aegis.db")
    SENSIBILIDAD_ALERTA = int(os.getenv("SENSIBILIDAD_ALERTA", "5"))
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

try:
    from utils.database import (  # type: ignore
        init_db, guardar_deteccion, obtener_historial,
        obtener_tendencia, guardar_zona, obtener_zonas,
    )
except ImportError:
    def init_db(): pass  # type: ignore
    def guardar_deteccion(*a, **kw): pass  # type: ignore
    def obtener_historial(limit=50): return []  # type: ignore
    def obtener_tendencia(*a): return []  # type: ignore
    def guardar_zona(*a): pass  # type: ignore
    def obtener_zonas(): return []  # type: ignore

try:
    from utils.ollama_analyst import OllamaAnalyst  # type: ignore
except ImportError:
    class OllamaAnalyst:  # type: ignore
        def __init__(self, *a, **kw): pass
        def is_available(self): return False
        def classify_threat_level(self, count, *a):
            if count == 0: return {"level": "VERDE", "action": "Monitor"}
            if count < 5:  return {"level": "AMARILLO", "action": "Heightened watch"}
            if count < 10: return {"level": "NARANJA", "action": "Alert command"}
            return {"level": "ROJO", "action": "Immediate response"}
        def analyze_detection(self, *a, **kw): return ""

try:
    from utils.temporal_analysis import TemporalAnalyzer  # type: ignore
except ImportError:
    class TemporalAnalyzer:  # type: ignore
        def __init__(self, *a, **kw): pass
        def analyze(self, *a, **kw): return None

try:
    from utils.gdelt import GdeltCrossReference  # type: ignore
except ImportError:
    class _GdeltResult:
        military_events = 0
        conflict_score = 0.0
        threat_correlation = "NONE"
        summary = "GDELT module not available."
        events = []

    class GdeltCrossReference:  # type: ignore
        def analyze(self, bbox, vehicles=0): return _GdeltResult()

# --- Auth ---
API_KEY = os.getenv('AEGIS_API_KEY', 'aegis-dev-key-change-in-production')
api_key_header = APIKeyHeader(name='X-API-Key', auto_error=True)


def verify_api_key(key: str = Security(api_key_header)) -> str:
    """Validate the X-API-Key header. Raises HTTP 403 on mismatch."""
    if key != API_KEY:
        raise HTTPException(status_code=403, detail="API Key invalida")
    return key


# --- App ---
app = FastAPI(
    title="AEGIS-IMINT API",
    description=(
        "REST API para integracion con sistemas C2 externos. "
        "Requiere cabecera X-API-Key en todas las peticiones."
    ),
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Middleware — order matters: rate limiter wraps CORS
app.add_middleware(RateLimitMiddleware, max_requests=60, window_seconds=60)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Init singletons
init_db()
analyst = OllamaAnalyst(OLLAMA_BASE_URL, OLLAMA_MODEL)
temporal = TemporalAnalyzer(DB_PATH)
gdelt_ref = GdeltCrossReference()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class BboxRequest(BaseModel):
    lon_min: float = Field(..., description="Longitud minima (WGS84)")
    lat_min: float = Field(..., description="Latitud minima (WGS84)")
    lon_max: float = Field(..., description="Longitud maxima (WGS84)")
    lat_max: float = Field(..., description="Latitud maxima (WGS84)")
    zone_name: str = Field(default="API Zone", description="Nombre descriptivo de la zona")


class AnalyzeRequest(BboxRequest):
    generate_report: bool = Field(
        default=False, description="Si es true, genera informe PDF en segundo plano"
    )
    alert_threshold: int = Field(
        default=SENSIBILIDAD_ALERTA,
        description="Numero de vehiculos que activa alertas",
    )


class ZoneRequest(BaseModel):
    nombre: str = Field(..., description="Nombre identificador de la zona")
    lon_min: float
    lat_min: float
    lon_max: float
    lat_max: float


class DetectionResponse(BaseModel):
    scan_id: str
    timestamp: str
    vehicle_count: int
    threat_level: str
    threat_action: str
    bbox: list
    llm_report: Optional[str] = None
    gdelt_summary: Optional[str] = None
    alert_sent: bool


class HistoryItem(BaseModel):
    timestamp: str
    vehicle_count: int
    threat_level: Optional[str] = None
    has_report: bool


class TemporalResponse(BaseModel):
    zone_label: str
    period_days: int
    mean_vehicles: float
    trend: str
    operational_tempo: str
    anomaly_days: List[str]
    summary: str


class StatusResponse(BaseModel):
    status: str
    version: str
    ollama_available: bool
    db_path: str
    timestamp: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/status", response_model=StatusResponse, tags=["Sistema"])
def get_status(key: str = Depends(verify_api_key)):
    """Estado del sistema AEGIS-IMINT: version, disponibilidad de Ollama y BD."""
    return StatusResponse(
        status="operational",
        version="2.0.0",
        ollama_available=analyst.is_available(),
        db_path=DB_PATH,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/api/analyze", response_model=DetectionResponse, tags=["Analisis"])
def analyze_zone(
    req: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    key: str = Depends(verify_api_key),
):
    """
    Analiza una zona geografica:
    1. Descarga imagen Sentinel-2 (si credenciales disponibles).
    2. Detecta vehiculos con YOLOv8.
    3. Genera informe IMINT con LLM y correlacion GDELT.
    4. Opcionalmente genera PDF en segundo plano.

    En modo demo (sin credenciales Sentinel) retorna datos sinteticos.
    """
    bbox = [req.lon_min, req.lat_min, req.lon_max, req.lat_max]
    scan_id = str(uuid.uuid4())[:8].upper()

    vehicle_count = 0
    img_path = ""
    classes: List[str] = []

    sentinel_ok = bool(os.getenv('SENTINEL_CLIENT_ID'))
    yolo_ok = os.path.exists(os.getenv('YOLO_MODEL_PATH', 'modelos/yolov8_military.pt'))

    if sentinel_ok and yolo_ok:
        try:
            from utils.sentinel import descargar_imagen  # type: ignore
            from utils.detector import detectar_vehiculos  # type: ignore
            img_path = descargar_imagen(bbox)
            vehicle_count, classes = detectar_vehiculos(img_path)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Error en analisis: {exc}")
    else:
        # Demo / sandbox mode — synthetic data
        import random
        vehicle_count = random.randint(0, 20)
        classes = ["vehicle"] * vehicle_count

    # Threat level
    threat = analyst.classify_threat_level(vehicle_count, "actual")

    # LLM report (optional — skipped if Ollama not running)
    llm_report = ""
    if analyst.is_available():
        llm_report = analyst.analyze_detection(vehicle_count, bbox, img_path or None)

    # GDELT cross-reference
    gdelt_result = gdelt_ref.analyze(bbox, vehicle_count)

    # Persist to database
    guardar_deteccion(
        vehicle_count, img_path, bbox,
        ', '.join(classes), threat['level'], llm_report,
    )

    # Alerts
    alert_sent = False
    if vehicle_count >= req.alert_threshold:
        try:
            from utils.alerts import enviar_alertas  # type: ignore
            results = enviar_alertas(vehicle_count, bbox, llm_report)
            alert_sent = any(results.values())
        except ImportError:
            pass

    # Optional async PDF generation
    if req.generate_report:
        background_tasks.add_task(
            _generate_pdf_background,
            scan_id, req.zone_name, bbox,
            vehicle_count, classes, threat['level'],
            llm_report, gdelt_result.summary,
        )

    return DetectionResponse(
        scan_id=scan_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        vehicle_count=vehicle_count,
        threat_level=threat['level'],
        threat_action=threat['action'],
        bbox=bbox,
        llm_report=llm_report or None,
        gdelt_summary=gdelt_result.summary or None,
        alert_sent=alert_sent,
    )


@app.get("/api/history", response_model=List[HistoryItem], tags=["Historial"])
def get_history(limit: int = 50, key: str = Depends(verify_api_key)):
    """Retorna las ultimas *limit* detecciones almacenadas en la base de datos."""
    rows = obtener_historial(limit)
    return [
        HistoryItem(
            timestamp=r[0],
            vehicle_count=r[1],
            threat_level=r[2] if len(r) > 2 else None,
            has_report=bool(r[3]) if len(r) > 3 else False,
        )
        for r in rows
    ]


@app.get(
    "/api/temporal",
    response_model=Optional[TemporalResponse],
    tags=["Analisis"],
)
def get_temporal(days: int = 30, key: str = Depends(verify_api_key)):
    """Analisis multitemporal de los ultimos *days* dias."""
    result = temporal.analyze(days_back=days)
    if result is None:
        return None
    return TemporalResponse(
        zone_label=result.zone_label,
        period_days=result.period_days,
        mean_vehicles=result.mean_vehicles,
        trend=result.trend,
        operational_tempo=result.operational_tempo,
        anomaly_days=result.anomaly_days,
        summary=result.summary,
    )


@app.post("/api/zones", tags=["Zonas"])
def create_zone(zone: ZoneRequest, key: str = Depends(verify_api_key)):
    """Registra una nueva zona de vigilancia en la base de datos."""
    bbox = [zone.lon_min, zone.lat_min, zone.lon_max, zone.lat_max]
    guardar_zona(zone.nombre, bbox)
    return {"status": "created", "nombre": zone.nombre, "bbox": bbox}


@app.get("/api/zones", tags=["Zonas"])
def list_zones(key: str = Depends(verify_api_key)):
    """Lista todas las zonas de vigilancia registradas."""
    zones = obtener_zonas()
    return [
        {
            "id": z[0],
            "nombre": z[1],
            "bbox": z[2],
            "activa": bool(z[3]),
        }
        for z in zones
    ]


@app.get("/api/gdelt", tags=["Analisis"])
def gdelt_query(
    lon_min: float,
    lat_min: float,
    lon_max: float,
    lat_max: float,
    vehicles: int = 0,
    key: str = Depends(verify_api_key),
):
    """Correlacion GDELT para una bounding-box geografica."""
    bbox = [lon_min, lat_min, lon_max, lat_max]
    result = gdelt_ref.analyze(bbox, vehicles)
    return {
        "bbox": bbox,
        "military_events": result.military_events,
        "conflict_score": result.conflict_score,
        "threat_correlation": result.threat_correlation,
        "summary": result.summary,
        "events": [
            {
                "date": e.date,
                "description": e.event_description[:150],
                "goldstein": e.goldstein_scale,
                "url": e.source_url,
            }
            for e in result.events[:5]
        ],
    }


@app.get("/api/reports/{filename}", tags=["Informes"])
def download_report(filename: str, key: str = Depends(verify_api_key)):
    """Descarga un informe PDF por nombre de archivo."""
    # Security: reject path traversal attempts
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Nombre de archivo invalido")
    if not filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos PDF")
    path = os.path.join("reports", filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Informe no encontrado")
    return FileResponse(path, media_type='application/pdf', filename=filename)


@app.get("/api/reports", tags=["Informes"])
def list_reports(key: str = Depends(verify_api_key)):
    """Lista todos los informes PDF disponibles en el directorio reports/."""
    reports_dir = "reports"
    if not os.path.exists(reports_dir):
        return []
    files = sorted(
        [f for f in os.listdir(reports_dir) if f.endswith('.pdf')],
        reverse=True,
    )
    return [
        {
            "filename": f,
            "size_kb": os.path.getsize(os.path.join(reports_dir, f)) // 1024,
        }
        for f in files
    ]


# ---------------------------------------------------------------------------
# Background helpers
# ---------------------------------------------------------------------------

def _generate_pdf_background(
    scan_id: str,
    zone_name: str,
    bbox: list,
    vehicle_count: int,
    classes: List[str],
    threat_level: str,
    llm_report: str,
    gdelt_summary: str,
) -> None:
    """Background task: generate a classified PDF report for an analysis scan."""
    try:
        from utils.report_generator import ImintReportGenerator, ImintReportData  # type: ignore
        gen = ImintReportGenerator()
        data = ImintReportData(
            report_id=scan_id,
            classification="RESTRINGIDO",
            generated_at=datetime.now(timezone.utc).isoformat(),
            operator_id="API-SYSTEM",
            zone_name=zone_name,
            bbox=bbox,
            vehicle_count=vehicle_count,
            vehicle_classes=classes,
            threat_level=threat_level,
            confidence_nato="B2",
            llm_report=llm_report,
            gdelt_summary=gdelt_summary,
        )
        out_path = gen.generate(data)
        import logging
        logging.getLogger("aegis.api").info("PDF report generated: %s", out_path)
    except Exception as exc:
        import logging
        logging.getLogger("aegis.api").error("PDF generation failed: %s", exc)
