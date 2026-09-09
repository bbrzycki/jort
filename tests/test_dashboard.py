"""Tests for live job persistence and the loopback monitor."""

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from jort import config
from jort import dashboard
from jort import database
from jort import detached
from jort import track_cli


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        data_dir = self.temporary_directory.name
        self.patches = [
            patch.object(config, "JORT_DIR", data_dir),
            patch.object(config, "CONFIG_PATH", os.path.join(data_dir, "config")),
            patch.object(config, "_get_data_dir", return_value=data_dir),
            patch.object(config, "_get_database_path", return_value=os.path.join(data_dir, "jort.db")),
        ]
        for item in self.patches:
            item.start()
        config._initialize_db()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temporary_directory.cleanup()

    def test_live_job_is_visible_with_metrics_and_output_before_completion(self):
        result = {}

        def run_job():
            result["payload"] = track_cli.track_new(
                [
                    sys.executable,
                    "-c",
                    "import time; print('first'); time.sleep(1.2); print('last')",
                ],
                to_db=True,
                session_name="dashboard-test",
                store_stdout=True,
                quiet=True,
            )

        thread = threading.Thread(target=run_job)
        thread.start()
        try:
            deadline = time.monotonic() + 3
            live_job = None
            while time.monotonic() < deadline:
                jobs = database.list_dashboard_jobs()
                if jobs and jobs[0].get("status") == "running" and jobs[0].get("metrics"):
                    live_job = jobs[0]
                    break
                time.sleep(0.02)

            self.assertIsNotNone(live_job)
            self.assertEqual(live_job["session_name"], "dashboard-test")
            self.assertIsNotNone(live_job["pid"])
            self.assertTrue(live_job["stdout_fn"])
            self.assertIn("peak_rss_bytes", live_job["metrics"])

            tail = dashboard.output_tail(live_job["job_id"])
            self.assertTrue(tail["available"])
            self.assertEqual(tail["source"], "live")
            self.assertIn("first", tail["text"])
        finally:
            thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["payload"]["status"], "success")

    def test_live_tail_bypasses_attachment_cap_and_exposes_build_estimate(self):
        result = {}

        def run_job():
            result["payload"] = track_cli.track_new(
                [
                    sys.executable,
                    "-c",
                    (
                        "import time; print('x' * 128, flush=True); time.sleep(.1); "
                        "print('[20/100] 20.0s F CXX example.o', flush=True); time.sleep(.7)"
                    ),
                ],
                to_db=True,
                session_name="live-tail-test",
                store_stdout=True,
                max_output_bytes=32,
                quiet=True,
            )

        thread = threading.Thread(target=run_job)
        thread.start()
        try:
            deadline = time.monotonic() + 3
            live_job = None
            while time.monotonic() < deadline:
                jobs = dashboard.snapshot()["active"]
                candidate = next(
                    (job for job in jobs if job["session_name"] == "live-tail-test"),
                    None,
                )
                if candidate and candidate["progress"]:
                    live_job = candidate
                    break
                time.sleep(0.02)

            self.assertIsNotNone(live_job)
            self.assertTrue(live_job["has_live_output"])
            self.assertEqual(live_job["progress"]["completed"], 20)
            self.assertEqual(live_job["progress"]["total"], 100)
            self.assertAlmostEqual(live_job["progress"]["remaining_seconds"], 80.0)

            tail = dashboard.output_tail(live_job["job_id"])
            self.assertEqual(tail["source"], "live")
            self.assertIn("[20/100] 20.0s", tail["text"])
            self.assertNotIn("output truncated at configured limit", tail["text"])
        finally:
            thread.join(timeout=5)
        self.assertFalse(thread.is_alive())

        archived = dashboard.output_tail(result["payload"]["job_id"])
        self.assertEqual(archived["source"], "captured")
        self.assertTrue(archived["capture_limited"])
        self.assertNotIn("output truncated at configured limit", archived["text"])
        archive_path = os.path.join(
            self.temporary_directory.name, result["payload"]["stdout_fn"]
        )
        with open(archive_path, encoding="utf-8") as stream:
            self.assertIn("output truncated at configured limit", stream.read())

    def test_siso_progress_parser_rejects_terminal_or_unqualified_lines(self):
        self.assertIsNone(dashboard._parse_siso_progress("[100/100] 12.0s LINK chrome"))
        self.assertIsNone(dashboard._parse_siso_progress("20/100 in 20 seconds"))

    def test_live_tail_writer_retains_recent_lines_without_attachment_marker(self):
        path = os.path.join(self.temporary_directory.name, "live-tail.log")
        writer = track_cli._LiveTailWriter(path, max_bytes=64, retain_bytes=32)
        try:
            writer.write("discarded\n" * 10)
            writer.write("[9/10] 9.0s F CXX final.o\n")
        finally:
            writer.close()
        with open(path, encoding="utf-8") as stream:
            text = stream.read()
        self.assertIn("[9/10] 9.0s", text)
        self.assertNotIn("output truncated at configured limit", text)

    def test_detached_job_is_persisted_before_its_worker_starts(self):
        def launch_worker(*args, **kwargs):
            del args, kwargs
            queued = database.get_job("detached-job")
            self.assertIsNotNone(queued)
            self.assertEqual(queued["status"], "queued")
            self.assertEqual(queued["session_id"], database.get_or_create_session("detached")[0])
            return SimpleNamespace(pid=4242)

        with patch.object(detached.subprocess, "Popen", side_effect=launch_worker):
            result = detached.launch({
                "job_id": "detached-job",
                "mode": "new",
                "command": "echo dashboard",
                "session_name": "detached",
            })

        self.assertEqual(result["job_id"], "detached-job")
        self.assertEqual(database.get_job("detached-job")["pid"], 4242)

    def test_snapshot_and_loopback_api_require_the_capability_token(self):
        payload = {
            "job_id": "finished-job",
            "session_id": database.get_or_create_session("history")[0],
            "name": "example command",
            "status": "success",
            "machine": "test-machine",
            "date_created": "2026-01-01T00:00:00+00:00",
            "date_modified": "2026-01-01T00:00:02+00:00",
            "runtime": 2.0,
            "stdout_fn": None,
            "error_message": None,
            "pid": None,
            "exit_code": 0,
            "metadata": {},
            "metrics": {"peak_rss_bytes": 42},
        }
        database.save_job(payload)
        monitor, url = dashboard.create_server(port=0, token="test-token")
        worker = threading.Thread(target=monitor.serve_forever, daemon=True)
        worker.start()
        try:
            with urlopen(url + "&unused=1", timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertNotIn("unsafe-inline", response.headers["Content-Security-Policy"])
                html = response.read().decode("utf-8")
            self.assertIn("data-job-id", html)
            self.assertNotIn("onclick=", html)
            with urlopen(url.replace("/?token=test-token", "/api/status?token=test-token"), timeout=2) as response:
                body = json.loads(response.read())
            self.assertEqual(body["history"][0]["job_id"], "finished-job")
            with self.assertRaises(HTTPError) as blocked:
                urlopen(url.replace("?token=test-token", ""), timeout=2)
            self.assertEqual(blocked.exception.code, 403)
        finally:
            monitor.shutdown()
            monitor.server_close()
            worker.join(timeout=2)

    def test_dashboard_rejects_non_loopback_binding(self):
        with self.assertRaises(ValueError):
            dashboard.create_server(host="0.0.0.0")


if __name__ == "__main__":
    unittest.main()
