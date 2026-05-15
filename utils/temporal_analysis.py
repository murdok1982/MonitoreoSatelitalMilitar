"""
Multitemporal Analysis — AEGIS-IMINT
Analyzes 30-day detection time series to identify patterns and anomalies.
"""
import sqlite3
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timedelta
import json


@dataclass
class TemporalPattern:
    zone_label: str
    period_days: int
    total_detections: int
    mean_vehicles: float
    std_vehicles: float
    peak_day: str
    peak_count: int
    trend: str                          # "ascending" | "descending" | "stable" | "erratic"
    trend_slope: float                  # vehicles/day
    anomaly_days: List[str] = field(default_factory=list)
    anomaly_counts: List[int] = field(default_factory=list)
    weekly_pattern: Dict[str, float] = field(default_factory=dict)  # day_of_week → avg
    operational_tempo: str = ""         # NATO-style tempo assessment
    summary: str = ""


class TemporalAnalyzer:
    def __init__(self, db_path: str, anomaly_threshold_sigma: float = 2.0):
        self.db_path = db_path
        self.sigma = anomaly_threshold_sigma

    def _load_series(self, bbox: Optional[list] = None,
                      days_back: int = 30) -> List[Tuple[datetime, int]]:
        """Load detection time series from DB, optionally filtered by bbox."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        since = (datetime.utcnow() - timedelta(days=days_back)).isoformat()

        if bbox:
            tol = 0.5
            c.execute("""SELECT timestamp, vehiculos_detectados FROM detecciones
                         WHERE timestamp >= ?
                         AND lon_min BETWEEN ? AND ?
                         AND lat_min BETWEEN ? AND ?
                         ORDER BY timestamp ASC""",
                      (since, bbox[0]-tol, bbox[0]+tol, bbox[1]-tol, bbox[1]+tol))
        else:
            c.execute("""SELECT timestamp, vehiculos_detectados FROM detecciones
                         WHERE timestamp >= ? ORDER BY timestamp ASC""", (since,))

        rows = c.fetchall()
        conn.close()

        series = []
        for ts_str, count in rows:
            try:
                ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00').replace('+00:00', ''))
                series.append((ts, int(count)))
            except ValueError:
                continue
        return series

    def _detect_anomalies(self, values: List[int]) -> List[int]:
        """Return indices of anomalous days (Z-score > sigma)."""
        if len(values) < 3:
            return []
        arr = np.array(values, dtype=float)
        mean, std = arr.mean(), arr.std()
        if std < 0.001:
            return []
        z_scores = np.abs((arr - mean) / std)
        return [i for i, z in enumerate(z_scores) if z >= self.sigma]

    def _compute_trend(self, values: List[int]) -> Tuple[str, float]:
        """Linear regression to get trend direction and slope."""
        if len(values) < 2:
            return "stable", 0.0
        x = np.arange(len(values), dtype=float)
        y = np.array(values, dtype=float)
        # Simple linear regression
        x_mean, y_mean = x.mean(), y.mean()
        denom = np.sum((x - x_mean) ** 2)
        if denom < 0.001:
            return "stable", 0.0
        slope = float(np.sum((x - x_mean) * (y - y_mean)) / denom)

        cv = float(np.std(y) / (np.mean(y) + 0.001))  # coefficient of variation

        if cv > 0.8:
            return "erratic", slope
        elif slope > 0.5:
            return "ascending", slope
        elif slope < -0.5:
            return "descending", slope
        else:
            return "stable", slope

    def _weekly_pattern(self, series: List[Tuple[datetime, int]]) -> Dict[str, float]:
        """Compute average vehicle count per day of week."""
        from collections import defaultdict
        buckets: dict = defaultdict(list)
        day_names = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
        for ts, count in series:
            buckets[day_names[ts.weekday()]].append(count)
        return {day: float(np.mean(vals)) for day, vals in buckets.items() if vals}

    def _nato_tempo(self, mean: float, trend: str, anomaly_count: int) -> str:
        """Classify operational tempo using NATO-like categories."""
        if mean == 0 and anomaly_count == 0:
            return "INACTIVO — Sin actividad detectada en el período"
        elif trend == "erratic":
            return "SURGE — Actividad irregular de alta variabilidad"
        elif anomaly_count >= 3:
            return "SURGE — Múltiples picos anómalos detectados"
        elif trend == "ascending" and mean >= 10:
            return "ESCALADA — Incremento progresivo de actividad"
        elif mean < 3 and trend == "stable":
            return "RUTINA — Actividad de bajo nivel, patrón regular"
        elif mean < 10 and trend in ("stable", "ascending"):
            return "SOSTENIDO — Actividad moderada consistente"
        elif trend == "descending":
            return "REPLIEGUE — Reducción de actividad"
        else:
            return "INDETERMINADO"

    def analyze(self, bbox: Optional[list] = None,
                 days_back: int = 30,
                 zone_label: str = "Zona global") -> Optional[TemporalPattern]:
        """Full temporal analysis. Returns None if insufficient data."""
        series = self._load_series(bbox, days_back)
        if not series:
            return None

        # Aggregate by day
        from collections import defaultdict
        daily: dict = defaultdict(int)
        for ts, count in series:
            day_key = ts.strftime('%Y-%m-%d')
            daily[day_key] = max(daily[day_key], count)  # max per day

        if not daily:
            return None

        dates = sorted(daily.keys())
        values = [daily[d] for d in dates]

        mean_v = float(np.mean(values))
        std_v = float(np.std(values))
        peak_idx = int(np.argmax(values))
        anomaly_idxs = self._detect_anomalies(values)
        trend, slope = self._compute_trend(values)
        weekly = self._weekly_pattern(series)
        tempo = self._nato_tempo(mean_v, trend, len(anomaly_idxs))

        summary = self._build_summary(zone_label, days_back, len(series),
                                       mean_v, std_v, trend, slope,
                                       len(anomaly_idxs), tempo)

        return TemporalPattern(
            zone_label=zone_label,
            period_days=days_back,
            total_detections=len(series),
            mean_vehicles=round(mean_v, 2),
            std_vehicles=round(std_v, 2),
            peak_day=dates[peak_idx],
            peak_count=values[peak_idx],
            trend=trend,
            trend_slope=round(slope, 3),
            anomaly_days=[dates[i] for i in anomaly_idxs],
            anomaly_counts=[values[i] for i in anomaly_idxs],
            weekly_pattern=weekly,
            operational_tempo=tempo,
            summary=summary,
        )

    def _build_summary(self, zone, days, n_scans, mean, std, trend, slope, n_anomalies, tempo):
        trend_desc = {
            'ascending': f'en ESCALADA (+{slope:.1f} vhc/día)',
            'descending': f'en REPLIEGUE ({slope:.1f} vhc/día)',
            'stable': 'ESTABLE',
            'erratic': 'ERRÁTICA (posible operación encubierta)',
        }.get(trend, '')
        return (f"Análisis temporal {days}d para '{zone}': {n_scans} escaneos, "
                f"media {mean:.1f}±{std:.1f} vhc/imagen. "
                f"Tendencia {trend_desc}. "
                f"{n_anomalies} días anómalos. "
                f"Tempo operacional: {tempo}.")


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------
import unittest


def _create_test_db(rows: list) -> str:
    """Create an in-memory-style SQLite DB file (temp) with test data.

    rows: list of (timestamp_iso, vehiculos_detectados, lon_min, lat_min)
    Returns path to temp DB file (caller must delete if needed).
    """
    import tempfile
    fd, path = tempfile.mkstemp(suffix='.db')
    import os; os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE detecciones (
        id INTEGER PRIMARY KEY,
        timestamp TEXT,
        vehiculos_detectados INTEGER,
        lon_min REAL DEFAULT 0.0,
        lat_min REAL DEFAULT 0.0
    )""")
    conn.executemany(
        "INSERT INTO detecciones (timestamp, vehiculos_detectados, lon_min, lat_min) VALUES (?,?,?,?)",
        rows
    )
    conn.commit()
    conn.close()
    return path


class TestTemporalPattern(unittest.TestCase):
    def test_dataclass_creation(self):
        p = TemporalPattern(
            zone_label="Zone A", period_days=30, total_detections=100,
            mean_vehicles=5.2, std_vehicles=2.1, peak_day="2024-01-15",
            peak_count=20, trend="ascending", trend_slope=0.8,
        )
        self.assertEqual(p.zone_label, "Zone A")
        self.assertEqual(p.trend, "ascending")
        self.assertEqual(p.anomaly_days, [])
        self.assertEqual(p.weekly_pattern, {})

    def test_defaults(self):
        p = TemporalPattern("z", 7, 0, 0.0, 0.0, "", 0, "stable", 0.0)
        self.assertEqual(p.operational_tempo, "")
        self.assertEqual(p.summary, "")


class TestDetectAnomalies(unittest.TestCase):
    def setUp(self):
        import tempfile, os
        self.db_path = _create_test_db([])
        self.analyzer = TemporalAnalyzer(self.db_path)

    def tearDown(self):
        import os
        os.unlink(self.db_path)

    def test_too_few_values(self):
        self.assertEqual(self.analyzer._detect_anomalies([5, 5]), [])

    def test_constant_series_no_anomalies(self):
        self.assertEqual(self.analyzer._detect_anomalies([10, 10, 10, 10, 10]), [])

    def test_clear_spike(self):
        # [2, 2, 2, 2, 100] — last value is a huge spike
        result = self.analyzer._detect_anomalies([2, 2, 2, 2, 100])
        self.assertIn(4, result)

    def test_lower_sigma_more_anomalies(self):
        a1 = TemporalAnalyzer(self.db_path, anomaly_threshold_sigma=3.0)
        a2 = TemporalAnalyzer(self.db_path, anomaly_threshold_sigma=0.5)
        values = [5, 5, 5, 5, 9, 5, 5, 5]
        r1 = a1._detect_anomalies(values)
        r2 = a2._detect_anomalies(values)
        self.assertLessEqual(len(r1), len(r2))

    def test_single_spike_index_correct(self):
        values = [5, 5, 5, 5, 5, 100, 5, 5]
        result = self.analyzer._detect_anomalies(values)
        self.assertIn(5, result)


class TestComputeTrend(unittest.TestCase):
    def setUp(self):
        self.db_path = _create_test_db([])
        self.analyzer = TemporalAnalyzer(self.db_path)

    def tearDown(self):
        import os
        os.unlink(self.db_path)

    def test_single_value(self):
        trend, slope = self.analyzer._compute_trend([5])
        self.assertEqual(trend, "stable")
        self.assertAlmostEqual(slope, 0.0)

    def test_ascending(self):
        trend, slope = self.analyzer._compute_trend([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        self.assertEqual(trend, "ascending")
        self.assertGreater(slope, 0.5)

    def test_descending(self):
        trend, slope = self.analyzer._compute_trend([10, 9, 8, 7, 6, 5, 4, 3, 2, 1])
        self.assertEqual(trend, "descending")
        self.assertLess(slope, -0.5)

    def test_stable(self):
        trend, slope = self.analyzer._compute_trend([5, 5, 5, 5, 5, 5, 5])
        self.assertEqual(trend, "stable")
        self.assertAlmostEqual(slope, 0.0, places=3)

    def test_erratic_high_cv(self):
        # High CV: values with huge variance relative to mean
        values = [1, 50, 1, 100, 1, 80, 1, 60, 1, 90]
        trend, slope = self.analyzer._compute_trend(values)
        self.assertEqual(trend, "erratic")

    def test_slope_direction_matches_trend(self):
        trend, slope = self.analyzer._compute_trend([1, 3, 5, 7, 9])
        self.assertGreater(slope, 0)


class TestWeeklyPattern(unittest.TestCase):
    def setUp(self):
        self.db_path = _create_test_db([])
        self.analyzer = TemporalAnalyzer(self.db_path)

    def tearDown(self):
        import os
        os.unlink(self.db_path)

    def test_empty_series(self):
        result = self.analyzer._weekly_pattern([])
        self.assertEqual(result, {})

    def test_single_day_of_week(self):
        # Monday 2024-01-01 is actually a Monday
        ts = datetime(2024, 1, 1, 12, 0)  # Monday
        series = [(ts, 10), (ts, 20)]
        result = self.analyzer._weekly_pattern(series)
        self.assertIn('Lun', result)
        self.assertAlmostEqual(result['Lun'], 15.0)

    def test_multiple_days(self):
        monday = datetime(2024, 1, 1)    # Monday
        tuesday = datetime(2024, 1, 2)   # Tuesday
        series = [(monday, 10), (monday, 20), (tuesday, 5)]
        result = self.analyzer._weekly_pattern(series)
        self.assertIn('Lun', result)
        self.assertIn('Mar', result)
        self.assertAlmostEqual(result['Lun'], 15.0)
        self.assertAlmostEqual(result['Mar'], 5.0)


class TestNatoTempo(unittest.TestCase):
    def setUp(self):
        self.db_path = _create_test_db([])
        self.analyzer = TemporalAnalyzer(self.db_path)

    def tearDown(self):
        import os
        os.unlink(self.db_path)

    def test_inactive(self):
        result = self.analyzer._nato_tempo(0, "stable", 0)
        self.assertIn("INACTIVO", result)

    def test_rutina(self):
        result = self.analyzer._nato_tempo(1.5, "stable", 0)
        self.assertIn("RUTINA", result)

    def test_sostenido_ascending(self):
        result = self.analyzer._nato_tempo(5.0, "ascending", 0)
        self.assertIn("SOSTENIDO", result)

    def test_escalada(self):
        result = self.analyzer._nato_tempo(15.0, "ascending", 0)
        self.assertIn("ESCALADA", result)

    def test_surge_erratic(self):
        result = self.analyzer._nato_tempo(8.0, "erratic", 0)
        self.assertIn("SURGE", result)

    def test_surge_anomalies(self):
        result = self.analyzer._nato_tempo(5.0, "stable", 5)
        self.assertIn("SURGE", result)

    def test_repliegue(self):
        result = self.analyzer._nato_tempo(4.0, "descending", 0)
        self.assertIn("REPLIEGUE", result)


class TestBuildSummary(unittest.TestCase):
    def setUp(self):
        self.db_path = _create_test_db([])
        self.analyzer = TemporalAnalyzer(self.db_path)

    def tearDown(self):
        import os
        os.unlink(self.db_path)

    def test_summary_contains_zone(self):
        s = self.analyzer._build_summary("Zona Norte", 30, 100, 5.0, 1.2,
                                          "ascending", 0.8, 2, "ESCALADA")
        self.assertIn("Zona Norte", s)
        self.assertIn("30d", s)
        self.assertIn("ESCALADA", s)

    def test_summary_descending(self):
        s = self.analyzer._build_summary("Zona Sur", 7, 50, 3.0, 0.5,
                                          "descending", -0.9, 0, "REPLIEGUE")
        self.assertIn("REPLIEGUE", s)

    def test_summary_erratic(self):
        s = self.analyzer._build_summary("Zona X", 14, 80, 8.0, 4.0,
                                          "erratic", 0.1, 3, "SURGE")
        self.assertIn("encubierta", s)

    def test_summary_anomaly_count(self):
        s = self.analyzer._build_summary("Z", 30, 10, 2.0, 1.0,
                                          "stable", 0.0, 3, "SURGE")
        self.assertIn("3 días anómalos", s)


class TestLoadSeries(unittest.TestCase):
    def test_empty_db_returns_empty(self):
        db = _create_test_db([])
        analyzer = TemporalAnalyzer(db)
        result = analyzer._load_series()
        self.assertEqual(result, [])
        import os; os.unlink(db)

    def test_recent_rows_loaded(self):
        now = datetime.utcnow()
        ts = (now - timedelta(days=1)).isoformat()
        db = _create_test_db([(ts, 5, 0.0, 0.0)])
        analyzer = TemporalAnalyzer(db)
        result = analyzer._load_series(days_back=30)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], 5)
        import os; os.unlink(db)

    def test_old_rows_excluded(self):
        now = datetime.utcnow()
        ts_old = (now - timedelta(days=60)).isoformat()
        ts_recent = (now - timedelta(days=1)).isoformat()
        db = _create_test_db([
            (ts_old, 10, 0.0, 0.0),
            (ts_recent, 5, 0.0, 0.0),
        ])
        analyzer = TemporalAnalyzer(db)
        result = analyzer._load_series(days_back=30)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], 5)
        import os; os.unlink(db)

    def test_invalid_timestamp_skipped(self):
        db = _create_test_db([("NOT-A-DATE", 5, 0.0, 0.0)])
        # The bad timestamp will be after the since filter (or fail parse)
        # We just verify no crash
        analyzer = TemporalAnalyzer(db)
        try:
            result = analyzer._load_series(days_back=30)
            # Bad timestamps should be skipped
        except Exception as e:
            self.fail(f"_load_series raised exception on bad timestamp: {e}")
        import os; os.unlink(db)

    def test_bbox_filter(self):
        now = datetime.utcnow()
        ts = (now - timedelta(days=1)).isoformat()
        db = _create_test_db([
            (ts, 5, 10.0, 20.0),   # inside bbox
            (ts, 8, 50.0, 60.0),   # outside bbox
        ])
        analyzer = TemporalAnalyzer(db)
        # bbox = [lon_min, lat_min, lon_max, lat_max]
        result = analyzer._load_series(bbox=[10.0, 20.0, 11.0, 21.0], days_back=30)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][1], 5)
        import os; os.unlink(db)


class TestAnalyze(unittest.TestCase):
    def test_empty_db_returns_none(self):
        db = _create_test_db([])
        analyzer = TemporalAnalyzer(db)
        result = analyzer.analyze()
        self.assertIsNone(result)
        import os; os.unlink(db)

    def test_single_record_returns_pattern(self):
        now = datetime.utcnow()
        ts = (now - timedelta(days=1)).isoformat()
        db = _create_test_db([(ts, 7, 0.0, 0.0)])
        analyzer = TemporalAnalyzer(db)
        result = analyzer.analyze(days_back=30, zone_label="Test Zone")
        self.assertIsNotNone(result)
        self.assertEqual(result.zone_label, "Test Zone")
        self.assertEqual(result.peak_count, 7)
        import os; os.unlink(db)

    def test_ascending_trend_detected(self):
        now = datetime.utcnow()
        rows = [
            ((now - timedelta(days=10 - i)).isoformat(), i * 3, 0.0, 0.0)
            for i in range(1, 11)
        ]
        db = _create_test_db(rows)
        analyzer = TemporalAnalyzer(db)
        result = analyzer.analyze(days_back=30)
        self.assertIsNotNone(result)
        self.assertIn(result.trend, ["ascending", "erratic"])
        import os; os.unlink(db)

    def test_peak_day_is_correct(self):
        now = datetime.utcnow()
        # Day 3 ago has 100 vehicles (peak), others have 5
        rows = [
            ((now - timedelta(days=5)).isoformat(), 5, 0.0, 0.0),
            ((now - timedelta(days=4)).isoformat(), 5, 0.0, 0.0),
            ((now - timedelta(days=3)).isoformat(), 100, 0.0, 0.0),
            ((now - timedelta(days=2)).isoformat(), 5, 0.0, 0.0),
            ((now - timedelta(days=1)).isoformat(), 5, 0.0, 0.0),
        ]
        db = _create_test_db(rows)
        analyzer = TemporalAnalyzer(db)
        result = analyzer.analyze(days_back=30)
        self.assertIsNotNone(result)
        expected_peak = (now - timedelta(days=3)).strftime('%Y-%m-%d')
        self.assertEqual(result.peak_day, expected_peak)
        self.assertEqual(result.peak_count, 100)
        import os; os.unlink(db)

    def test_anomaly_detection_in_analyze(self):
        now = datetime.utcnow()
        # 9 normal days + 1 huge spike
        rows = [
            ((now - timedelta(days=10 - i)).isoformat(), 5, 0.0, 0.0)
            for i in range(9)
        ]
        rows.append(((now - timedelta(days=1)).isoformat(), 200, 0.0, 0.0))
        db = _create_test_db(rows)
        analyzer = TemporalAnalyzer(db, anomaly_threshold_sigma=2.0)
        result = analyzer.analyze(days_back=30)
        self.assertIsNotNone(result)
        self.assertGreater(len(result.anomaly_days), 0)
        import os; os.unlink(db)

    def test_multiple_records_same_day_takes_max(self):
        now = datetime.utcnow()
        ts = (now - timedelta(days=1)).isoformat()
        rows = [(ts, 5, 0.0, 0.0), (ts, 15, 0.0, 0.0), (ts, 10, 0.0, 0.0)]
        db = _create_test_db(rows)
        analyzer = TemporalAnalyzer(db)
        result = analyzer.analyze(days_back=30)
        self.assertIsNotNone(result)
        # max per day → 15
        self.assertEqual(result.peak_count, 15)
        import os; os.unlink(db)

    def test_result_has_summary(self):
        now = datetime.utcnow()
        ts = (now - timedelta(days=2)).isoformat()
        db = _create_test_db([(ts, 10, 0.0, 0.0)])
        analyzer = TemporalAnalyzer(db)
        result = analyzer.analyze(zone_label="Zona Alfa")
        self.assertIsNotNone(result)
        self.assertIn("Zona Alfa", result.summary)
        self.assertGreater(len(result.summary), 20)
        import os; os.unlink(db)

    def test_period_days_respected(self):
        now = datetime.utcnow()
        ts_recent = (now - timedelta(days=5)).isoformat()
        ts_old = (now - timedelta(days=45)).isoformat()
        db = _create_test_db([
            (ts_recent, 10, 0.0, 0.0),
            (ts_old, 999, 0.0, 0.0),
        ])
        analyzer = TemporalAnalyzer(db)
        result = analyzer.analyze(days_back=30)
        self.assertIsNotNone(result)
        # The old record (999) should not be included
        self.assertEqual(result.peak_count, 10)
        import os; os.unlink(db)


if __name__ == '__main__':
    unittest.main(verbosity=2)
