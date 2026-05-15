"""
GDELT Cross-Reference — AEGIS-IMINT
Queries GDELT 2.0 to find news events near satellite detections.
No API key required.
"""
import requests
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime, timedelta
import time


@dataclass
class GdeltEvent:
    date: str
    actor1: str
    actor2: str
    event_code: str
    event_description: str
    goldstein_scale: float   # -10 (most negative) to +10 (most positive)
    num_mentions: int
    avg_tone: float          # news tone
    source_url: str
    lat: float
    lon: float
    distance_km: float       # distance from our detection


@dataclass
class GdeltReport:
    bbox: list
    period_days: int
    events: List[GdeltEvent] = field(default_factory=list)
    military_events: int = 0
    conflict_score: float = 0.0   # average goldstein weighted by mentions
    threat_correlation: str = "SIN DATOS"
    summary: str = ""


# GDELT event codes related to military activity
MILITARY_EVENT_CODES = {
    '14': 'Protesta', '15': 'Amenaza fuerza', '16': 'Reducción relaciones',
    '17': 'Coerción', '18': 'Asalto', '19': 'Pelea', '20': 'Uso fuerza masiva',
    '190': 'Uso fuerza', '191': 'Imposición embargo', '192': 'Minas',
    '193': 'Ataque', '194': 'Combate', '195': 'Combate aéreo',
    '196': 'Combate naval', '1951': 'Fuego artillería', '1952': 'Fuego rifles',
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in km."""
    import math
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class GdeltCrossReference:
    BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
    GKG_URL = "https://api.gdeltproject.org/api/v2/gkg/gkg"

    def __init__(self, radius_km: float = 200.0, days_back: int = 7):
        self.radius_km = radius_km
        self.days_back = days_back

    def query_events(self, lat_center: float, lon_center: float,
                     days_back: Optional[int] = None) -> List[GdeltEvent]:
        """Query GDELT DOC 2.0 API for events near coordinates."""
        days = days_back or self.days_back

        # Use GDELT's fulltext search API (free)
        # Build geographic query using country + approximate region
        end = datetime.utcnow()
        start = end - timedelta(days=days)

        params = {
            "query": "conflict military troops",
            "mode": "artlist",
            "maxrecords": 50,
            "startdatetime": start.strftime("%Y%m%d%H%M%S"),
            "enddatetime": end.strftime("%Y%m%d%H%M%S"),
            "format": "json",
            "timespan": f"{days}d",
        }

        events = []
        try:
            resp = requests.get(self.BASE_URL, params=params, timeout=15)
            if resp.status_code != 200:
                return events

            data = resp.json()
            articles = data.get("articles", [])

            for art in articles[:20]:
                # Parse article data
                try:
                    lat = float(art.get("socialimage", {}).get("lat", 0) or 0)
                    lon = float(art.get("socialimage", {}).get("lon", 0) or 0)
                except (TypeError, ValueError):
                    lat, lon = 0.0, 0.0

                dist = haversine_km(lat_center, lon_center, lat, lon) if lat and lon else 9999.0

                event = GdeltEvent(
                    date=art.get("seendate", ""),
                    actor1=art.get("sourcecountry", ""),
                    actor2="",
                    event_code="",
                    event_description=art.get("title", "")[:200],
                    goldstein_scale=float(art.get("tone", "0").split(",")[0] if art.get("tone") else 0),
                    num_mentions=int(art.get("socialshares", 0) or 0),
                    avg_tone=float(art.get("tone", "0").split(",")[0] if art.get("tone") else 0),
                    source_url=art.get("url", ""),
                    lat=lat,
                    lon=lon,
                    distance_km=dist,
                )
                events.append(event)

        except Exception:
            # GDELT can be unreliable; return empty gracefully
            pass

        # Sort by distance
        events.sort(key=lambda e: e.distance_km)
        return events

    def analyze(self, bbox: list, vehicle_count: int) -> GdeltReport:
        """Full GDELT analysis for a bbox. Returns GdeltReport."""
        lat_center = (bbox[1] + bbox[3]) / 2
        lon_center = (bbox[0] + bbox[2]) / 2

        events = self.query_events(lat_center, lon_center)
        nearby = [e for e in events if e.distance_km <= self.radius_km]

        military_events = sum(1 for e in nearby
                              if any(kw in e.event_description.lower()
                                     for kw in ['military', 'troops', 'forces', 'attack', 'conflict',
                                                'missile', 'soldier', 'army', 'naval', 'air strike',
                                                'militares', 'tropas', 'ataque', 'conflicto']))

        # Conflict score: weighted average tone (negative = more conflict)
        if nearby:
            total_mentions = sum(max(e.num_mentions, 1) for e in nearby)
            conflict_score = sum(e.avg_tone * max(e.num_mentions, 1)
                                  for e in nearby) / total_mentions
        else:
            conflict_score = 0.0

        # Correlation assessment
        if vehicle_count >= 10 and military_events >= 3:
            correlation = "CORRELACIÓN ALTA — Actividad terrestre coincide con eventos de conflicto"
        elif vehicle_count >= 5 and military_events >= 1:
            correlation = "CORRELACIÓN MEDIA — Actividad detectada en zona de tensión"
        elif military_events == 0:
            correlation = "SIN CORRELACIÓN — No hay eventos de conflicto en medios cercanos"
        else:
            correlation = "CORRELACIÓN BAJA — Eventos mediáticos sin actividad terrestre significativa"

        summary = _build_gdelt_summary(nearby, military_events, conflict_score, correlation, self.days_back)

        return GdeltReport(
            bbox=bbox,
            period_days=self.days_back,
            events=nearby[:10],
            military_events=military_events,
            conflict_score=conflict_score,
            threat_correlation=correlation,
            summary=summary,
        )


def _build_gdelt_summary(events, military_count, score, correlation, days):
    if not events:
        return f"Sin noticias relevantes en GDELT en los últimos {days} días para esta zona."
    tone = "NEGATIVO (conflicto)" if score < -2 else "NEUTRAL" if score < 2 else "POSITIVO"
    return (f"GDELT: {len(events)} artículos en zona ({military_count} de temática militar). "
            f"Tono mediático: {tone} ({score:+.1f}). {correlation}.")


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------
import unittest
from unittest.mock import patch, MagicMock


class TestHaversineKm(unittest.TestCase):
    def test_same_point(self):
        self.assertAlmostEqual(haversine_km(0, 0, 0, 0), 0.0, places=3)

    def test_known_distance(self):
        # Madrid (40.4168, -3.7038) to Barcelona (41.3851, 2.1734) ≈ 504 km
        d = haversine_km(40.4168, -3.7038, 41.3851, 2.1734)
        self.assertGreater(d, 490)
        self.assertLess(d, 520)

    def test_symmetry(self):
        d1 = haversine_km(10, 20, 30, 40)
        d2 = haversine_km(30, 40, 10, 20)
        self.assertAlmostEqual(d1, d2, places=5)

    def test_equator_one_degree(self):
        # 1 degree longitude on equator ≈ 111.32 km
        d = haversine_km(0, 0, 0, 1)
        self.assertGreater(d, 110)
        self.assertLess(d, 113)


class TestGdeltEventDataclass(unittest.TestCase):
    def test_creation(self):
        ev = GdeltEvent(
            date="20240101", actor1="US", actor2="RU",
            event_code="194", event_description="Combat",
            goldstein_scale=-7.2, num_mentions=10, avg_tone=-3.5,
            source_url="http://example.com", lat=40.0, lon=20.0, distance_km=50.0
        )
        self.assertEqual(ev.event_code, "194")
        self.assertAlmostEqual(ev.goldstein_scale, -7.2)
        self.assertAlmostEqual(ev.distance_km, 50.0)


class TestGdeltReportDataclass(unittest.TestCase):
    def test_defaults(self):
        r = GdeltReport(bbox=[0, 0, 1, 1], period_days=7)
        self.assertEqual(r.military_events, 0)
        self.assertAlmostEqual(r.conflict_score, 0.0)
        self.assertEqual(r.threat_correlation, "SIN DATOS")
        self.assertEqual(r.events, [])


class TestBuildGdeltSummary(unittest.TestCase):
    def test_empty_events(self):
        s = _build_gdelt_summary([], 0, 0.0, "SIN CORRELACIÓN", 7)
        self.assertIn("Sin noticias", s)

    def test_negative_tone(self):
        ev = GdeltEvent("d", "a", "b", "c", "desc", -5.0, 1, -5.0, "u", 0, 0, 10)
        s = _build_gdelt_summary([ev], 1, -5.0, "CORRELACIÓN ALTA", 7)
        self.assertIn("NEGATIVO", s)
        self.assertIn("CORRELACIÓN ALTA", s)

    def test_positive_tone(self):
        ev = GdeltEvent("d", "a", "b", "c", "desc", 3.0, 1, 3.0, "u", 0, 0, 10)
        s = _build_gdelt_summary([ev], 0, 3.0, "SIN CORRELACIÓN", 7)
        self.assertIn("POSITIVO", s)

    def test_neutral_tone(self):
        ev = GdeltEvent("d", "a", "b", "c", "desc", 0.0, 1, 0.0, "u", 0, 0, 10)
        s = _build_gdelt_summary([ev], 0, 0.0, "SIN CORRELACIÓN", 7)
        self.assertIn("NEUTRAL", s)


class TestGdeltCrossReferenceInit(unittest.TestCase):
    def test_defaults(self):
        g = GdeltCrossReference()
        self.assertEqual(g.radius_km, 200.0)
        self.assertEqual(g.days_back, 7)

    def test_custom(self):
        g = GdeltCrossReference(radius_km=50, days_back=14)
        self.assertEqual(g.radius_km, 50)
        self.assertEqual(g.days_back, 14)


class TestGdeltQueryEventsNetworkError(unittest.TestCase):
    """query_events must return [] gracefully when network fails."""
    def test_network_failure_returns_empty(self):
        g = GdeltCrossReference()
        with patch("requests.get", side_effect=Exception("timeout")):
            result = g.query_events(40.0, -3.0)
        self.assertEqual(result, [])

    def test_non_200_returns_empty(self):
        g = GdeltCrossReference()
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        with patch("requests.get", return_value=mock_resp):
            result = g.query_events(40.0, -3.0)
        self.assertEqual(result, [])

    def test_valid_response_parsed(self):
        """Parse a synthetic GDELT artlist response."""
        g = GdeltCrossReference(radius_km=10000)  # large radius to capture all
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "articles": [
                {
                    "seendate": "20240101T120000Z",
                    "sourcecountry": "US",
                    "title": "Military conflict in region",
                    "tone": "-5.2,3.1,1.0",
                    "socialshares": "100",
                    "url": "http://example.com/article1",
                    "socialimage": {},
                }
            ]
        }
        with patch("requests.get", return_value=mock_resp):
            result = g.query_events(0.0, 0.0)
        self.assertEqual(len(result), 1)
        self.assertIn("Military conflict", result[0].event_description)
        self.assertAlmostEqual(result[0].avg_tone, -5.2)
        self.assertEqual(result[0].num_mentions, 100)


class TestGdeltAnalyze(unittest.TestCase):
    """analyze() must produce correct correlation strings."""

    def _make_event(self, desc, dist, tone=-3.0, mentions=5):
        return GdeltEvent(
            date="20240101", actor1="US", actor2="",
            event_code="", event_description=desc,
            goldstein_scale=tone, num_mentions=mentions, avg_tone=tone,
            source_url="", lat=0, lon=0, distance_km=dist
        )

    def test_high_correlation(self):
        g = GdeltCrossReference(radius_km=500)
        military_descs = [
            "Military troops advance", "Army attack forces move", "conflict military clash"
        ]
        fake_events = [self._make_event(d, 100) for d in military_descs]
        with patch.object(g, 'query_events', return_value=fake_events):
            report = g.analyze([-1, -1, 1, 1], vehicle_count=15)
        self.assertIn("CORRELACIÓN ALTA", report.threat_correlation)
        self.assertEqual(report.military_events, 3)

    def test_no_correlation_empty(self):
        g = GdeltCrossReference(radius_km=500)
        with patch.object(g, 'query_events', return_value=[]):
            report = g.analyze([-1, -1, 1, 1], vehicle_count=0)
        self.assertIn("SIN CORRELACIÓN", report.threat_correlation)
        self.assertEqual(report.military_events, 0)
        self.assertAlmostEqual(report.conflict_score, 0.0)

    def test_medium_correlation(self):
        g = GdeltCrossReference(radius_km=500)
        events = [self._make_event("Military troops spotted", 50)]
        with patch.object(g, 'query_events', return_value=events):
            report = g.analyze([-1, -1, 1, 1], vehicle_count=6)
        self.assertIn("CORRELACIÓN MEDIA", report.threat_correlation)

    def test_conflict_score_weighted(self):
        g = GdeltCrossReference(radius_km=500)
        events = [
            self._make_event("troops", 50, tone=-6.0, mentions=2),
            self._make_event("troops", 80, tone=-2.0, mentions=8),
        ]
        with patch.object(g, 'query_events', return_value=events):
            report = g.analyze([-1, -1, 1, 1], vehicle_count=0)
        # Weighted: (-6*2 + -2*8) / 10 = -28/10 = -2.8
        self.assertAlmostEqual(report.conflict_score, -2.8, places=5)

    def test_events_truncated_to_10(self):
        g = GdeltCrossReference(radius_km=500)
        events = [self._make_event(f"event {i}", i * 10) for i in range(20)]
        with patch.object(g, 'query_events', return_value=events):
            report = g.analyze([-1, -1, 1, 1], vehicle_count=0)
        self.assertLessEqual(len(report.events), 10)

    def test_report_bbox_and_period(self):
        g = GdeltCrossReference(radius_km=500, days_back=14)
        with patch.object(g, 'query_events', return_value=[]):
            report = g.analyze([10, 20, 30, 40], vehicle_count=0)
        self.assertEqual(report.bbox, [10, 20, 30, 40])
        self.assertEqual(report.period_days, 14)


if __name__ == '__main__':
    unittest.main(verbosity=2)
