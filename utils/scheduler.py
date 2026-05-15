"""
Watchdog Scheduler — AEGIS-IMINT
Automatically scans all saved zones on a configured interval.
"""
import threading
import time
import logging
from datetime import datetime
from typing import Callable, Optional
import os

logger = logging.getLogger(__name__)


class WatchdogJob:
    def __init__(self, zone_id: int, nombre: str, bbox: list, callback: Callable):
        self.zone_id = zone_id
        self.nombre = nombre
        self.bbox = bbox
        self.callback = callback
        self.last_run: Optional[datetime] = None
        self.last_result: Optional[dict] = None
        self.error_count: int = 0


class AegisWatchdog:
    """
    Background watchdog that runs zone scans on a configurable interval.
    Uses threading (not APScheduler) for zero extra dependencies.
    """

    def __init__(self, interval_seconds: int = 3600, max_errors: int = 5):
        self.interval = interval_seconds
        self.max_errors = max_errors
        self._jobs: dict = {}  # int -> WatchdogJob
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False
        self._lock = threading.Lock()

    def register_zone(self, zone_id: int, nombre: str, bbox: list, callback: Callable):
        """Register a zone for periodic scanning."""
        with self._lock:
            self._jobs[zone_id] = WatchdogJob(zone_id, nombre, bbox, callback)
        logger.debug("Watchdog: registered zone '%s' (id=%d)", nombre, zone_id)

    def unregister_zone(self, zone_id: int):
        """Remove a zone from periodic scanning."""
        with self._lock:
            removed = self._jobs.pop(zone_id, None)
        if removed:
            logger.debug("Watchdog: unregistered zone id=%d", zone_id)

    def start(self):
        """Start the background watchdog thread."""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("AEGIS Watchdog started (interval=%ds)", self.interval)

    def stop(self):
        """Signal the watchdog to stop and wait for thread to exit."""
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("AEGIS Watchdog stopped.")

    def is_running(self) -> bool:
        """Return True if the watchdog thread is alive."""
        return self._running and (self._thread is not None) and self._thread.is_alive()

    def status(self) -> dict:
        """Return current watchdog status as a serialisable dict."""
        with self._lock:
            return {
                "running": self.is_running(),
                "zones": len(self._jobs),
                "interval_seconds": self.interval,
                "jobs": [
                    {
                        "zone_id": j.zone_id,
                        "nombre": j.nombre,
                        "last_run": j.last_run.isoformat() if j.last_run else None,
                        "error_count": j.error_count,
                        "last_result": j.last_result,
                    }
                    for j in self._jobs.values()
                ],
            }

    def _run_loop(self):
        """Main loop: iterate over all jobs and execute those that are due."""
        while not self._stop_event.is_set():
            with self._lock:
                jobs_snapshot = list(self._jobs.values())

            for job in jobs_snapshot:
                if self._stop_event.is_set():
                    break
                now = datetime.utcnow()
                if job.last_run is None or (now - job.last_run).total_seconds() >= self.interval:
                    self._execute_job(job)

            # Sleep in small increments to allow fast shutdown
            for _ in range(min(60, max(1, self.interval))):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

    def _execute_job(self, job: WatchdogJob):
        """Execute a single job's callback, tracking errors."""
        try:
            logger.info("Watchdog: scanning zone '%s' (id=%d)", job.nombre, job.zone_id)
            result = job.callback(job.zone_id, job.nombre, job.bbox)
            job.last_run = datetime.utcnow()
            job.last_result = result or {"status": "ok"}
            job.error_count = 0
            logger.info("Watchdog: zone '%s' scan complete: %s", job.nombre, result)
        except Exception as e:
            job.error_count += 1
            job.last_run = datetime.utcnow()
            job.last_result = {"status": "error", "message": str(e)}
            logger.error("Watchdog: zone '%s' scan failed (%d/%d): %s",
                         job.nombre, job.error_count, self.max_errors, e)
            if job.error_count >= self.max_errors:
                logger.warning("Watchdog: zone '%s' suspended after %d errors",
                               job.nombre, self.max_errors)
                with self._lock:
                    self._jobs.pop(job.zone_id, None)


# ---------------------------------------------------------------------------
# Singleton helpers
# ---------------------------------------------------------------------------

_watchdog: Optional[AegisWatchdog] = None
_watchdog_lock = threading.Lock()


def get_watchdog(interval_seconds: int = 3600) -> AegisWatchdog:
    """Return (and lazily create) the singleton AegisWatchdog instance."""
    global _watchdog
    with _watchdog_lock:
        if _watchdog is None:
            _watchdog = AegisWatchdog(interval_seconds=interval_seconds)
    return _watchdog


def reset_watchdog():
    """Reset the singleton (useful for testing)."""
    global _watchdog
    with _watchdog_lock:
        if _watchdog is not None and _watchdog.is_running():
            _watchdog.stop()
        _watchdog = None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    import unittest

    class TestAegisWatchdog(unittest.TestCase):

        def setUp(self):
            # Each test gets a fresh watchdog with a very short interval
            self.wd = AegisWatchdog(interval_seconds=1, max_errors=3)

        def tearDown(self):
            if self.wd.is_running():
                self.wd.stop()

        # ------------------------------------------------------------------
        # Lifecycle tests
        # ------------------------------------------------------------------

        def test_start_stop_lifecycle(self):
            """start() makes is_running() True; stop() makes it False."""
            self.assertFalse(self.wd.is_running())
            self.wd.start()
            time.sleep(0.1)
            self.assertTrue(self.wd.is_running())
            self.wd.stop()
            self.assertFalse(self.wd.is_running())

        def test_double_start_is_idempotent(self):
            """Calling start() twice should not raise or create two threads."""
            self.wd.start()
            thread_id_1 = id(self.wd._thread)
            self.wd.start()  # second call must be a no-op
            thread_id_2 = id(self.wd._thread)
            self.assertEqual(thread_id_1, thread_id_2)
            self.wd.stop()

        # ------------------------------------------------------------------
        # Register / unregister tests
        # ------------------------------------------------------------------

        def test_register_zone(self):
            """Registered zones appear in status()."""
            self.wd.register_zone(1, "Zone Alpha", [10.0, 20.0, 11.0, 21.0],
                                  lambda *a: {"status": "ok"})
            st = self.wd.status()
            self.assertEqual(st["zones"], 1)
            self.assertEqual(st["jobs"][0]["zone_id"], 1)
            self.assertEqual(st["jobs"][0]["nombre"], "Zone Alpha")

        def test_unregister_zone(self):
            """Unregistered zones disappear from status()."""
            self.wd.register_zone(1, "Zone Alpha", [], lambda *a: None)
            self.wd.register_zone(2, "Zone Bravo", [], lambda *a: None)
            self.wd.unregister_zone(1)
            st = self.wd.status()
            self.assertEqual(st["zones"], 1)
            self.assertEqual(st["jobs"][0]["zone_id"], 2)

        def test_unregister_nonexistent_is_safe(self):
            """Unregistering a zone that doesn't exist must not raise."""
            self.wd.unregister_zone(999)  # should be a no-op

        # ------------------------------------------------------------------
        # Callback invocation test
        # ------------------------------------------------------------------

        def test_callback_called_within_expected_time(self):
            """With interval=0.1 s, the callback should fire within ~1 second."""
            wd = AegisWatchdog(interval_seconds=1, max_errors=3)
            # We exploit that last_run is None → job runs immediately on first loop pass
            called = threading.Event()

            def fake_scan(zone_id, nombre, bbox):
                called.set()
                return {"vehicles": 0}

            wd.register_zone(42, "TestZone", [0, 0, 1, 1], fake_scan)
            wd.start()
            fired = called.wait(timeout=3.0)
            wd.stop()
            self.assertTrue(fired, "Callback was not called within 3 seconds")

        # ------------------------------------------------------------------
        # Error counting and zone suspension tests
        # ------------------------------------------------------------------

        def test_error_counting(self):
            """Each callback exception increments error_count."""
            wd = AegisWatchdog(interval_seconds=1, max_errors=5)

            def bad_scan(*args):
                raise RuntimeError("Simulated sensor failure")

            wd.register_zone(7, "BadZone", [], bad_scan)
            wd.start()
            time.sleep(0.5)   # let it execute once immediately
            wd.stop()

            # The job may have been suspended or have errors > 0
            # (exact count depends on timing; just verify it incremented)
            st = wd.status()
            # Either the job was removed (suspended) or error_count > 0
            job_list = st["jobs"]
            if job_list:
                self.assertGreater(job_list[0]["error_count"], 0)
            # else: job was already suspended (also valid)

        def test_zone_removed_after_max_errors(self):
            """Zone is suspended (removed) after max_errors consecutive failures."""
            wd = AegisWatchdog(interval_seconds=1, max_errors=2)
            call_count = [0]

            def always_fails(*args):
                call_count[0] += 1
                raise ValueError("Simulated failure")

            wd.register_zone(99, "FailZone", [], always_fails)
            # Execute the job manually (bypass threading) for determinism
            job = wd._jobs[99]
            for _ in range(2):
                wd._execute_job(job)

            # After 2 failures with max_errors=2, zone should be removed
            self.assertNotIn(99, wd._jobs)

        # ------------------------------------------------------------------
        # Status dict structure test
        # ------------------------------------------------------------------

        def test_status_structure(self):
            """status() must contain required keys."""
            st = self.wd.status()
            self.assertIn("running", st)
            self.assertIn("zones", st)
            self.assertIn("interval_seconds", st)
            self.assertIn("jobs", st)
            self.assertEqual(st["interval_seconds"], 1)

        # ------------------------------------------------------------------
        # Singleton helper tests
        # ------------------------------------------------------------------

        def test_get_watchdog_returns_singleton(self):
            """get_watchdog() always returns the same instance."""
            reset_watchdog()
            wd1 = get_watchdog(interval_seconds=60)
            wd2 = get_watchdog(interval_seconds=60)
            self.assertIs(wd1, wd2)
            reset_watchdog()

    unittest.main(verbosity=2)
