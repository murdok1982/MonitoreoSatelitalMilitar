"""
PDF Report Generator — AEGIS-IMINT
Generates classified IMINT reports in PDF format.
Uses fpdf2 (pure Python, no external system deps).
"""
from fpdf import FPDF, XPos, YPos
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime, timezone
import os
import hashlib
import base64


@dataclass
class ImintReportData:
    report_id: str
    classification: str           # "RESTRINGIDO", "CONFIDENCIAL", "SECRETO"
    generated_at: str             # ISO8601 UTC
    operator_id: str
    zone_name: str
    bbox: list                    # [lon_min, lat_min, lon_max, lat_max]

    # Detection results
    vehicle_count: int
    vehicle_classes: List[str]
    threat_level: str             # VERDE/AMARILLO/NARANJA/ROJO
    confidence_nato: str          # "A1", "B2", "C3" etc

    # Images
    satellite_image_path: Optional[str] = None
    annotated_image_path: Optional[str] = None
    change_image_path: Optional[str] = None

    # Analysis
    llm_report: str = ""
    gdelt_summary: str = ""
    temporal_summary: str = ""

    # History (for trend chart)
    trend_dates: List[str] = field(default_factory=list)
    trend_counts: List[int] = field(default_factory=list)


class AegisReportPDF(FPDF):
    """Custom FPDF subclass with AEGIS-IMINT header/footer."""

    CLASSIFICATION_COLORS = {
        "RESTRINGIDO": (255, 165, 0),    # Orange
        "CONFIDENCIAL": (255, 0, 0),     # Red
        "SECRETO": (128, 0, 128),        # Purple
        "SIN CLASIFICAR": (0, 128, 0),   # Green
    }

    def __init__(self, classification: str = "RESTRINGIDO"):
        super().__init__()
        self.classification = classification
        self.cl_color = self.CLASSIFICATION_COLORS.get(classification, (200, 0, 0))

    def header(self):
        # Classification banner
        self.set_fill_color(*self.cl_color)
        self.rect(0, 0, 210, 10, 'F')
        self.set_font('Helvetica', 'B', 9)
        self.set_text_color(255, 255, 255)
        self.cell(0, 10, f'// {self.classification} // AEGIS-IMINT // {self.classification} //',
                  align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def footer(self):
        self.set_y(-20)
        self.set_fill_color(*self.cl_color)
        self.rect(0, 287, 210, 10, 'F')
        self.set_font('Helvetica', 'I', 7)
        self.set_text_color(255, 255, 255)
        ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        self.cell(0, 10,
                  f'AEGIS-IMINT | Pag. {self.page_no()} | {ts} | {self.classification}',
                  align='C')

    def chapter_title(self, title: str):
        self.set_font('Helvetica', 'B', 12)
        self.set_fill_color(30, 30, 60)
        self.set_text_color(255, 255, 255)
        self.cell(0, 8, f'  {title}', fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)
        self.ln(3)

    def body_text(self, text: str):
        self.set_font('Helvetica', '', 9)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5, text)
        self.ln(2)

    def key_value(self, key: str, value: str, key_color=(50, 50, 150)):
        label_w = 52
        value_w = self.epw - label_w  # effective page width minus label
        x_start = self.get_x()
        y_start = self.get_y()

        # Render label cell
        self.set_font('Helvetica', 'B', 9)
        self.set_text_color(*key_color)
        self.cell(label_w, 6, f'{key}:', border=0,
                  new_x=XPos.RIGHT, new_y=YPos.LAST)

        # Render value — record position then multi_cell, then align Y
        self.set_font('Helvetica', '', 9)
        self.set_text_color(0, 0, 0)
        x_val = self.get_x()
        self.multi_cell(value_w, 6, str(value), border=0)
        # Ensure next call starts on a fresh left-margin line
        self.set_x(x_start)

    def threat_badge(self, level: str):
        colors = {
            'VERDE': (0, 150, 0), 'AMARILLO': (200, 180, 0),
            'NARANJA': (220, 100, 0), 'ROJO': (200, 0, 0),
        }
        c = colors.get(level, (100, 100, 100))
        self.set_fill_color(*c)
        self.set_text_color(255, 255, 255)
        self.set_font('Helvetica', 'B', 14)
        self.cell(0, 12, f'  NIVEL DE AMENAZA: {level}',
                  fill=True, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(0, 0, 0)
        self.ln(4)


class ImintReportGenerator:
    def __init__(self, output_dir: str = 'reports'):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    @staticmethod
    def compute_fingerprint(data: 'ImintReportData') -> str:
        """Compute deterministic SHA-256 fingerprint of key report fields."""
        fingerprint_data = (
            f"{data.report_id}{data.generated_at}"
            f"{data.vehicle_count}{data.threat_level}"
        ).encode()
        return hashlib.sha256(fingerprint_data).hexdigest()

    def generate(self, data: ImintReportData) -> str:
        """Generate PDF report. Returns file path."""
        pdf = AegisReportPDF(classification=data.classification)
        pdf.set_auto_page_break(auto=True, margin=25)
        pdf.add_page()

        # ── PORTADA ──
        pdf.set_font('Helvetica', 'B', 20)
        pdf.set_text_color(30, 30, 80)
        pdf.ln(5)
        pdf.cell(0, 12, 'INFORME IMINT - AEGIS', align='C',
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('Helvetica', 'B', 14)
        pdf.cell(0, 8, 'Monitoreo Satelital Militar', align='C',
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(5)

        pdf.threat_badge(data.threat_level)

        # ── SECCIÓN 1: IDENTIFICACIÓN ──
        pdf.chapter_title('1. IDENTIFICACION DEL INFORME')
        pdf.key_value('ID Informe', data.report_id)
        pdf.key_value('Clasificacion', data.classification)
        pdf.key_value('Generado', data.generated_at)
        pdf.key_value('Operador', data.operator_id)
        pdf.key_value('Zona', data.zone_name)
        pdf.key_value('Coordenadas (WGS84)',
                      f"Lon: {data.bbox[0]:.4f}-{data.bbox[2]:.4f} | "
                      f"Lat: {data.bbox[1]:.4f}-{data.bbox[3]:.4f}")
        pdf.ln(3)

        # ── SECCIÓN 2: RESUMEN EJECUTIVO ──
        pdf.chapter_title('2. RESUMEN EJECUTIVO')
        pdf.key_value('Vehiculos detectados', str(data.vehicle_count))
        pdf.key_value('Clases identificadas', ', '.join(set(data.vehicle_classes)) or 'N/A')
        pdf.key_value('Nivel de amenaza', data.threat_level)
        pdf.key_value('Confianza NATO', data.confidence_nato)
        pdf.ln(3)

        # ── SECCIÓN 3: IMÁGENES ──
        if data.satellite_image_path and os.path.exists(data.satellite_image_path):
            pdf.chapter_title('3. IMAGEN SATELITAL')
            try:
                pdf.image(data.satellite_image_path, w=160, h=0)
                pdf.ln(2)
                pdf.set_font('Helvetica', 'I', 7)
                pdf.cell(0, 4, 'Fuente: Sentinel-2 L1C - Copernicus Programme (ESA)',
                         new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            except Exception:
                pdf.body_text('[Imagen no disponible]')

        if data.annotated_image_path and os.path.exists(data.annotated_image_path):
            if pdf.get_y() > 200:
                pdf.add_page()
            pdf.chapter_title('3b. IMAGEN ANOTADA - DETECCIONES')
            try:
                pdf.image(data.annotated_image_path, w=160, h=0)
            except Exception:
                pdf.body_text('[Imagen anotada no disponible]')

        if data.change_image_path and os.path.exists(data.change_image_path):
            if pdf.get_y() > 200:
                pdf.add_page()
            pdf.chapter_title('3c. ANALISIS DE CAMBIOS')
            try:
                pdf.image(data.change_image_path, w=160, h=0)
            except Exception:
                pdf.body_text('[Imagen de cambios no disponible]')

        # ── SECCIÓN 4: ANÁLISIS IMINT ──
        pdf.add_page()
        pdf.chapter_title('4. ANALISIS DE INTELIGENCIA (IMINT)')
        if data.llm_report:
            pdf.body_text(data.llm_report[:3000])
        else:
            pdf.body_text('Analisis LLM no disponible.')

        # ── SECCIÓN 5: CORRELACIÓN GDELT ──
        pdf.chapter_title('5. CORRELACION MEDIATICA (GDELT)')
        pdf.body_text(data.gdelt_summary or 'Analisis GDELT no ejecutado.')

        # ── SECCIÓN 6: ANÁLISIS TEMPORAL ──
        pdf.chapter_title('6. ANALISIS MULTITEMPORAL')
        pdf.body_text(data.temporal_summary or 'Analisis temporal no disponible.')

        # Simple ASCII trend chart if data available
        if data.trend_dates and data.trend_counts and len(data.trend_counts) > 1:
            max_v = max(data.trend_counts) or 1
            pdf.set_font('Courier', '', 7)
            chart_lines = []
            for d, v in zip(data.trend_dates[-14:], data.trend_counts[-14:]):
                bar = '#' * int(v / max_v * 30)
                chart_lines.append(f"{d[-5:]} |{bar:<30}| {v:3d}")
            pdf.multi_cell(0, 4, '\n'.join(chart_lines))

        # ── SECCIÓN 7: FIRMA DIGITAL ──
        pdf.add_page()
        pdf.chapter_title('7. INTEGRIDAD DEL DOCUMENTO')

        fingerprint = self.compute_fingerprint(data)
        fingerprint_data = (
            f"{data.report_id}{data.generated_at}"
            f"{data.vehicle_count}{data.threat_level}"
        ).encode()

        pdf.key_value('SHA-256 del Informe', fingerprint)
        pdf.key_value('Generado por', 'AEGIS-IMINT v2.0 - Sistema automatizado')
        pdf.key_value('Nota legal',
                      'Este documento es CLASIFICADO. Su distribucion esta restringida '
                      'a personal con habilitacion de seguridad adecuada. '
                      'La reproduccion no autorizada esta penada por ley.')
        pdf.ln(10)
        pdf.set_font('Helvetica', 'I', 8)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 5,
                 'Firma Digital Electronica (simulada - integrar con HSM para produccion)',
                 new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font('Courier', '', 7)
        sig_b64 = base64.b64encode(fingerprint_data).decode()[:64]
        pdf.cell(0, 5, f'SIG: {sig_b64}...', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Save
        ts = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        filename = f"AEGIS_IMINT_{data.report_id}_{ts}.pdf"
        out_path = os.path.join(self.output_dir, filename)
        pdf.output(out_path)
        return out_path
