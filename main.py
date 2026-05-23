"""
import hispan_shield_guardian  # noqa: F401
AEGIS-IMINT — Sistema de Monitoreo Satelital Militar
Detección de vehículos militares via Sentinel-2 + YOLOv8 + Ollama

ARQUITECTURA:
  - Streamlit UI (sin while True — usa button-driven session_state)
  - Sentinel Hub para imágenes satelitales Sentinel-2
  - YOLOv8 para detección de vehículos militares
  - Ollama LLM (llava) para análisis IMINT táctico
  - Fernet para cifrado de datos sensibles
  - SQLite con conexiones thread-safe (abrir/cerrar por función)
"""
import streamlit as st
import folium
import folium.plugins
from streamlit_folium import st_folium
import time
import os
from datetime import datetime

from config import (
    SENSIBILIDAD_ALERTA,
    UPDATE_INTERVAL,
    YOLO_MODEL_PATH,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    FERNET_KEY_PATH,
    IMAGES_DIR,
    DB_PATH,
)
from utils.database import (
    init_db,
    guardar_deteccion,
    obtener_historial,
    obtener_tendencia,
    guardar_zona,
    obtener_zonas,
)
from utils.alerts import enviar_alertas
from utils.ollama_analyst import OllamaAnalyst
from utils.crypto import load_or_create_key

# ─── Inicialización (una sola vez por sesión de Streamlit) ────────────────────
init_db()

# Inicializar clave Fernet (se crea si no existe)
try:
    _fernet_key = load_or_create_key(FERNET_KEY_PATH)
except Exception:
    _fernet_key = None  # Sin cifrado si el directorio no es accesible

analyst = OllamaAnalyst(OLLAMA_BASE_URL, OLLAMA_MODEL)

# ─── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AEGIS-IMINT | Monitoreo Satelital Militar",
    page_icon="🦅",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Session state defaults ───────────────────────────────────────────────────
if 'current_bbox' not in st.session_state:
    st.session_state['current_bbox'] = None
if 'last_analysis' not in st.session_state:
    st.session_state['last_analysis'] = None
if 'monitoring_active' not in st.session_state:
    st.session_state['monitoring_active'] = False

# ─── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        "<h2 style='color:#3ddc84;font-family:monospace'>🦅 AEGIS-IMINT</h2>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    modo = st.radio(
        "Modo operacional:",
        ["🗺️ Monitoreo en Vivo", "📊 Historial / Análisis", "🗂️ Zonas Guardadas"],
    )

    st.markdown("---")
    st.markdown("### Estado del Sistema")

    ollama_ok = analyst.is_available()
    yolo_ok = os.path.exists(YOLO_MODEL_PATH)
    sentinel_configured = bool(os.getenv('SENTINEL_CLIENT_ID'))

    st.markdown(f"{'🟢' if ollama_ok else '🔴'} Ollama (`{OLLAMA_MODEL}`)")
    st.markdown(f"{'🟢' if yolo_ok else '🔴'} Modelo YOLO")
    st.markdown(f"{'🟢' if sentinel_configured else '🔴'} Sentinel Hub API")
    st.markdown(f"{'🟢' if _fernet_key else '🔴'} Cifrado Fernet")

# ─── Cabecera principal ───────────────────────────────────────────────────────
st.markdown(
    """
<div style='text-align:center;padding:12px;
            background:linear-gradient(90deg,#0d1b2a,#1b3a4b);
            border-radius:10px;margin-bottom:20px'>
  <h1 style='color:#3ddc84;font-family:monospace'>🦅 AEGIS-IMINT</h1>
  <p style='color:#aaa'>Sistema de Monitoreo Satelital Militar — Detección Táctica por IA</p>
</div>
""",
    unsafe_allow_html=True,
)

# =============================================================================
# MODO 1 — MONITOREO EN VIVO
# =============================================================================
if modo == "🗺️ Monitoreo en Vivo":
    col_map, col_ctrl = st.columns([2, 1])

    with col_map:
        st.subheader("📍 Define la Zona de Vigilancia")
        st.caption("Usa la herramienta de dibujo para trazar un polígono sobre el área de interés.")

        m = folium.Map(location=[40.0, 15.0], zoom_start=5, tiles="CartoDB dark_matter")
        folium.plugins.Draw(
            export=False,
            draw_options={
                "polyline": False,
                "polygon": True,
                "circle": False,
                "rectangle": True,
                "marker": False,
                "circlemarker": False,
            },
        ).add_to(m)

        draw_result = st_folium(m, width=700, height=460, key="main_map")

    with col_ctrl:
        st.subheader("🎛️ Control de Misión")

        nombre_zona = st.text_input(
            "Nombre de zona:",
            value=f"Zona_{datetime.utcnow().strftime('%H%M')}",
        )
        guardar_btn = st.button("💾 Guardar Zona")

        st.markdown("---")

        intervalo_min = st.slider(
            "Intervalo monitoreo automático (min):",
            min_value=10,
            max_value=180,
            value=UPDATE_INTERVAL // 60,
        )
        umbral = st.slider(
            "Umbral de alerta (vehículos):",
            min_value=1,
            max_value=50,
            value=SENSIBILIDAD_ALERTA,
        )

        st.markdown("---")
        iniciar_btn = st.button(
            "🚀 Iniciar Análisis",
            type="primary",
            use_container_width=True,
            help="Descarga imagen Sentinel-2 y ejecuta detección YOLOv8",
        )

        if st.session_state['last_analysis']:
            st.caption(f"Último análisis: {st.session_state['last_analysis']}")

    # ── Procesar área dibujada ────────────────────────────────────────────────
    if draw_result and draw_result.get("last_active_drawing"):
        geom = draw_result["last_active_drawing"]["geometry"]
        coords_raw = geom["coordinates"][0]

        bbox = [
            min(c[0] for c in coords_raw),
            min(c[1] for c in coords_raw),
            max(c[0] for c in coords_raw),
            max(c[1] for c in coords_raw),
        ]
        st.session_state["current_bbox"] = bbox

        st.info(
            f"Zona activa: lon [{bbox[0]:.4f}, {bbox[2]:.4f}] "
            f"/ lat [{bbox[1]:.4f}, {bbox[3]:.4f}]"
        )

        if guardar_btn and nombre_zona:
            guardar_zona(nombre_zona, bbox)
            st.success(f"Zona '{nombre_zona}' guardada correctamente.")

        # ── Análisis bajo demanda (no while True) ────────────────────────────
        if iniciar_btn:
            if not sentinel_configured:
                st.error(
                    "Sentinel Hub no configurado. "
                    "Edita el archivo `.env` con tus credenciales SENTINEL_CLIENT_ID y SENTINEL_CLIENT_SECRET."
                )

            elif not yolo_ok:
                # Modo demostración sin modelo real
                st.warning(
                    "Modelo YOLO no encontrado en `modelos/`. "
                    "Ejecutando en modo demostración con datos simulados."
                )
                with st.spinner("Simulando análisis..."):
                    time.sleep(2)

                n_sim = 7
                threat = analyst.classify_threat_level(n_sim, "estable")

                c1, c2 = st.columns(2)
                c1.metric("Vehículos detectados (sim)", n_sim)
                c2.metric("Nivel de amenaza", threat["level"])
                st.info(threat["action"])

                if ollama_ok:
                    with st.spinner("Generando informe IMINT con Ollama..."):
                        informe = analyst.analyze_detection(n_sim, bbox)
                    with st.expander("📋 Informe IMINT (modo demo)"):
                        st.markdown(informe)

                st.session_state["last_analysis"] = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

            else:
                # ── Flujo real: Sentinel → YOLO → Ollama ─────────────────────
                progress = st.progress(0, text="Descargando imagen satelital Sentinel-2...")
                result_placeholder = st.empty()

                try:
                    from utils.sentinel import descargar_imagen
                    img_path = descargar_imagen(bbox)
                    progress.progress(40, text="Detectando vehículos con YOLOv8...")

                    from utils.detector import detectar_vehiculos
                    cantidad, clases = detectar_vehiculos(img_path)
                    progress.progress(70, text="Analizando nivel de amenaza...")

                    informe = ""
                    if ollama_ok:
                        with st.spinner("Generando informe IMINT con Ollama AEGIS..."):
                            informe = analyst.analyze_detection(cantidad, bbox, img_path)

                    threat = analyst.classify_threat_level(cantidad, "actual")
                    progress.progress(90, text="Guardando registro en base de datos...")

                    guardar_deteccion(
                        cantidad,
                        img_path,
                        bbox,
                        clases=", ".join(clases),
                        amenaza=threat["level"],
                        informe=informe,
                    )

                    alerta_status = {}
                    if cantidad >= umbral:
                        alerta_status = enviar_alertas(cantidad, bbox, informe)

                    progress.progress(100, text="Análisis completado.")

                    # ── Resultados ────────────────────────────────────────────
                    st.image(
                        img_path,
                        caption=f"Sentinel-2 | {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
                    )

                    c1, c2, c3 = st.columns(3)
                    c1.metric("Vehículos detectados", cantidad)
                    c2.metric("Nivel de amenaza", threat["level"])
                    c3.metric("Umbral de alerta", f"{umbral} vhc")

                    if cantidad >= umbral:
                        email_ok = alerta_status.get("email", False)
                        tg_ok = alerta_status.get("telegram", False)
                        st.error(
                            f"ALERTA ACTIVADA — "
                            f"Email: {'✓' if email_ok else '✗'} | "
                            f"Telegram: {'✓' if tg_ok else '✗'}"
                        )
                    else:
                        st.success("Sin actividad anómala. Por debajo del umbral de alerta.")

                    st.markdown(f"**Clases detectadas:** `{', '.join(clases) or 'N/A'}`")
                    st.info(threat["action"])

                    if informe:
                        with st.expander("📋 Informe IMINT Completo"):
                            st.markdown(informe)

                    st.session_state["last_analysis"] = datetime.utcnow().strftime(
                        "%Y-%m-%d %H:%M UTC"
                    )

                except Exception as exc:
                    progress.empty()
                    st.error(f"Error en análisis: {exc}")

        # ── Botón de monitoreo continuo (session_state, no while True) ────────
        st.markdown("---")
        st.subheader("🔄 Monitoreo Continuo")

        if not st.session_state["monitoring_active"]:
            if st.button("▶ Activar monitoreo automático", key="start_monitoring"):
                st.session_state["monitoring_active"] = True
                st.rerun()
        else:
            if st.button("⏹ Detener monitoreo", key="stop_monitoring", type="secondary"):
                st.session_state["monitoring_active"] = False
                st.rerun()

            st.info(
                f"Monitoreo activo — intervalo: {intervalo_min} min. "
                "Cada ciclo requiere recargar manualmente o usar st.rerun() con un timer externo."
            )
            # Nota: en producción usar APScheduler o Celery para el loop real.
            # st.rerun() aquí causaría un loop de renders; el intervalo real debe
            # gestionarse con un scheduler externo o un thread daemon separado.

    else:
        st.info("👆 Dibuja un rectángulo o polígono en el mapa para definir la zona de vigilancia.")

# =============================================================================
# MODO 2 — HISTORIAL / ANÁLISIS
# =============================================================================
elif modo == "📊 Historial / Análisis":
    st.subheader("📊 Historial de Detecciones")

    historial = obtener_historial(200)
    tendencia = obtener_tendencia()

    if not historial:
        st.warning("Sin detecciones registradas. Inicia un monitoreo primero.")
    else:
        # Gráfica de tendencia
        if len(tendencia) > 1:
            import pandas as pd

            df = pd.DataFrame(tendencia, columns=["Timestamp", "Vehículos"])
            df["Timestamp"] = pd.to_datetime(df["Timestamp"])
            df = df.set_index("Timestamp")
            st.subheader("Tendencia de detecciones")
            st.line_chart(df)

        # Métricas resumen
        total = len(historial)
        max_v = max(r[1] for r in historial)
        alertas = sum(1 for r in historial if r[2] in ("ROJO", "NARANJA"))

        cm1, cm2, cm3 = st.columns(3)
        cm1.metric("Total detecciones", total)
        cm2.metric("Máx. vehículos", max_v)
        cm3.metric("Alertas generadas", alertas)

        st.markdown("---")
        st.markdown("### Últimas 20 detecciones")

        COLOR_MAP = {
            "ROJO": "🔴",
            "NARANJA": "🟠",
            "AMARILLO": "🟡",
            "VERDE": "🟢",
        }

        for row in historial[:20]:
            ts, vehiculos, amenaza, img_path, informe = row
            icon = COLOR_MAP.get(amenaza, "⚪")
            label = f"{icon} {ts} — {vehiculos} vehículos — {amenaza or 'N/A'}"

            with st.expander(label):
                if img_path and os.path.exists(img_path):
                    st.image(img_path, width=450)
                else:
                    st.caption("Imagen no disponible.")
                if informe:
                    st.markdown(informe)

# =============================================================================
# MODO 3 — ZONAS GUARDADAS
# =============================================================================
elif modo == "🗂️ Zonas Guardadas":
    st.subheader("🗂️ Zonas de Vigilancia Guardadas")

    zonas = obtener_zonas()

    if not zonas:
        st.info("No hay zonas guardadas. Dibuja y guarda zonas en el modo de Monitoreo en Vivo.")
    else:
        for zona_id, nombre, coords, activa in zonas:
            col1, col2, col3 = st.columns([3, 1, 1])
            col1.markdown(f"**{nombre}**  \n`{coords}`")

            if col2.button("▶ Seleccionar", key=f"sel_{zona_id}"):
                st.session_state["current_bbox"] = coords
                st.success(f"Zona '{nombre}' activada. Ve a Monitoreo en Vivo para analizarla.")

            if col3.button("🗑️ Eliminar", key=f"del_{zona_id}"):
                import sqlite3
                from config import DB_PATH as _DB
                _conn = sqlite3.connect(_DB)
                _conn.execute(
                    "UPDATE zonas_vigilancia SET activa=0 WHERE id=?", (zona_id,)
                )
                _conn.commit()
                _conn.close()
                st.rerun()

# ─── Footer ───────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<p style='text-align:center;color:#555;font-size:12px'>"
    "AEGIS-IMINT v2.0 | Clasificación: RESTRINGIDO | "
    "Sistema defensivo autorizado | "
    f"UTC {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
    "</p>",
    unsafe_allow_html=True,
)
