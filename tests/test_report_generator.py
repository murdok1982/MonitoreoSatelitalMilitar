"""
Unit tests for ImintReportGenerator (utils/report_generator.py).
Run: python3 -m pytest tests/test_report_generator.py -v
  or: python3 -m unittest tests.test_report_generator -v
"""
import os
import sys
import hashlib
import tempfile
import unittest

# Allow imports from the package root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.report_generator import ImintReportData, ImintReportGenerator


def _minimal_data(**kwargs) -> ImintReportData:
    """Return a minimal ImintReportData suitable for tests."""
    defaults = dict(
        report_id="TEST001",
        classification="RESTRINGIDO",
        generated_at="2025-01-01T00:00:00Z",
        operator_id="OPR-01",
        zone_name="Zona Alpha",
        bbox=[-3.7, 40.4, -3.6, 40.5],
        vehicle_count=5,
        vehicle_classes=["tank", "truck", "apc"],
        threat_level="AMARILLO",
        confidence_nato="B2",
    )
    defaults.update(kwargs)
    return ImintReportData(**defaults)


class TestImintReportGeneratorOutput(unittest.TestCase):
    """Verify that generate() produces a valid PDF file."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="aegis_test_")
        self.gen = ImintReportGenerator(output_dir=self.tmp_dir)

    def test_generate_returns_string_path(self):
        data = _minimal_data()
        result = self.gen.generate(data)
        self.assertIsInstance(result, str, "generate() must return a file path string")

    def test_generate_creates_pdf_file(self):
        data = _minimal_data()
        result = self.gen.generate(data)
        self.assertTrue(os.path.exists(result), f"PDF file not found at: {result}")

    def test_generated_file_has_pdf_extension(self):
        data = _minimal_data()
        result = self.gen.generate(data)
        self.assertTrue(result.endswith('.pdf'), "Output file must have .pdf extension")

    def test_generated_file_is_not_empty(self):
        data = _minimal_data()
        result = self.gen.generate(data)
        size = os.path.getsize(result)
        self.assertGreater(size, 1024, f"PDF is suspiciously small ({size} bytes)")

    def test_generated_file_starts_with_pdf_magic(self):
        """PDF files must start with %PDF-"""
        data = _minimal_data()
        result = self.gen.generate(data)
        with open(result, 'rb') as fh:
            header = fh.read(5)
        self.assertEqual(header, b'%PDF-', "File does not appear to be a valid PDF")

    def test_report_id_in_filename(self):
        data = _minimal_data(report_id="RPTABC")
        result = self.gen.generate(data)
        self.assertIn("RPTABC", os.path.basename(result))

    def test_output_dir_is_created_automatically(self):
        new_dir = os.path.join(self.tmp_dir, "subdir", "reports")
        gen = ImintReportGenerator(output_dir=new_dir)
        self.assertTrue(os.path.isdir(new_dir))

    def test_generate_with_trend_data(self):
        """Trend chart section is exercised without errors."""
        data = _minimal_data(
            trend_dates=["2025-01-01", "2025-01-02", "2025-01-03"],
            trend_counts=[3, 7, 5],
        )
        result = self.gen.generate(data)
        self.assertTrue(os.path.exists(result))

    def test_generate_with_llm_report(self):
        data = _minimal_data(llm_report="Analysis: multiple armoured vehicles detected.")
        result = self.gen.generate(data)
        self.assertTrue(os.path.exists(result))

    def test_generate_with_all_optional_text_fields(self):
        data = _minimal_data(
            llm_report="LLM analysis text.",
            gdelt_summary="GDELT: 3 military events detected.",
            temporal_summary="Temporal: increasing trend over 30 days.",
        )
        result = self.gen.generate(data)
        self.assertTrue(os.path.exists(result))

    def test_generate_secreto_classification(self):
        data = _minimal_data(classification="SECRETO")
        result = self.gen.generate(data)
        self.assertTrue(os.path.exists(result))

    def test_generate_multiple_reports_distinct_files(self):
        """Each call must produce a distinct file (timestamp in name)."""
        import time
        data1 = _minimal_data(report_id="R1")
        data2 = _minimal_data(report_id="R2")
        path1 = self.gen.generate(data1)
        time.sleep(1)   # ensure timestamp differs
        path2 = self.gen.generate(data2)
        self.assertNotEqual(path1, path2)

    def test_nonexistent_image_paths_are_skipped_gracefully(self):
        """Missing image paths must not raise exceptions."""
        data = _minimal_data(
            satellite_image_path="/nonexistent/sat.png",
            annotated_image_path="/nonexistent/ann.png",
            change_image_path="/nonexistent/chg.png",
        )
        result = self.gen.generate(data)
        self.assertTrue(os.path.exists(result))


class TestFingerprintDeterminism(unittest.TestCase):
    """Verify the SHA-256 fingerprint is deterministic for identical inputs."""

    def _make_data(self, **kwargs):
        return _minimal_data(**kwargs)

    def test_same_inputs_same_fingerprint(self):
        d1 = self._make_data(
            report_id="FP001",
            generated_at="2025-06-01T12:00:00Z",
            vehicle_count=10,
            threat_level="ROJO",
        )
        d2 = self._make_data(
            report_id="FP001",
            generated_at="2025-06-01T12:00:00Z",
            vehicle_count=10,
            threat_level="ROJO",
        )
        fp1 = ImintReportGenerator.compute_fingerprint(d1)
        fp2 = ImintReportGenerator.compute_fingerprint(d2)
        self.assertEqual(fp1, fp2, "Fingerprint must be deterministic for identical inputs")

    def test_different_report_id_different_fingerprint(self):
        d1 = self._make_data(report_id="AAA")
        d2 = self._make_data(report_id="BBB")
        self.assertNotEqual(
            ImintReportGenerator.compute_fingerprint(d1),
            ImintReportGenerator.compute_fingerprint(d2),
        )

    def test_different_threat_level_different_fingerprint(self):
        d1 = self._make_data(threat_level="VERDE")
        d2 = self._make_data(threat_level="ROJO")
        self.assertNotEqual(
            ImintReportGenerator.compute_fingerprint(d1),
            ImintReportGenerator.compute_fingerprint(d2),
        )

    def test_different_vehicle_count_different_fingerprint(self):
        d1 = self._make_data(vehicle_count=0)
        d2 = self._make_data(vehicle_count=99)
        self.assertNotEqual(
            ImintReportGenerator.compute_fingerprint(d1),
            ImintReportGenerator.compute_fingerprint(d2),
        )

    def test_fingerprint_is_valid_sha256_hex(self):
        d = self._make_data()
        fp = ImintReportGenerator.compute_fingerprint(d)
        self.assertEqual(len(fp), 64, "SHA-256 hex digest must be 64 characters")
        # Must be valid hex
        int(fp, 16)

    def test_fingerprint_matches_manual_computation(self):
        """Fingerprint must match a manual SHA-256 of the same concatenated string."""
        d = self._make_data(
            report_id="MANUAL01",
            generated_at="2025-01-15T08:30:00Z",
            vehicle_count=7,
            threat_level="NARANJA",
        )
        raw = f"{d.report_id}{d.generated_at}{d.vehicle_count}{d.threat_level}".encode()
        expected = hashlib.sha256(raw).hexdigest()
        self.assertEqual(ImintReportGenerator.compute_fingerprint(d), expected)

    def test_fingerprint_stable_across_calls(self):
        """Calling compute_fingerprint multiple times returns the same value."""
        d = self._make_data(report_id="STABLE", vehicle_count=3)
        results = {ImintReportGenerator.compute_fingerprint(d) for _ in range(5)}
        self.assertEqual(len(results), 1, "Fingerprint must not change across repeated calls")


if __name__ == '__main__':
    unittest.main(verbosity=2)
