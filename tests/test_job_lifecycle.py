"""Regression tests for process results, persistence, and callback isolation."""

import contextlib
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import click

from jort import jort_exe
from jort import tracker
from jort import track_cli
from jort import database
from jort import config


class FailingCallback:
    channel = "email"

    def execute(self, payload):
        raise RuntimeError("smtp unavailable")


class SucceedingCallback:
    channel = "text"

    def execute(self, payload):
        return {"id": "message-1"}


class JobLifecycleTests(unittest.TestCase):
    def test_successful_output_containing_exception_is_success(self):
        payload = track_cli.track_new(
            "python -c 'print(\"Exception: ordinary output\")'",
            quiet=True,
        )
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["exit_code"], 0)

    def test_timeout_is_a_failure_with_a_result_code(self):
        payload = track_cli.track_new(
            "python -c 'import time; time.sleep(1)'",
            timeout_seconds=0.05,
            quiet=True,
        )
        self.assertEqual(payload["status"], "timeout")
        self.assertIn("process exceeded", payload["error_message"])
        self.assertIsNotNone(payload["exit_code"])

    def test_existing_pid_monitor_handles_unreaped_child(self):
        process = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(0.05)"]
        )
        try:
            payload = track_cli.track_existing(process.pid)
        finally:
            process.wait()
        self.assertEqual(payload["status"], "finished")
        self.assertFalse(payload["metadata"]["exit_status_known"])

    def test_child_exit_code_reaches_cli(self):
        payload = track_cli.track_new(
            "python -c 'import sys; sys.exit(7)'",
            quiet=True,
        )
        self.assertEqual(payload["exit_code"], 7)
        self.assertEqual(payload["status"], "error")
        with self.assertRaises(click.exceptions.Exit):
            jort_exe._emit_result(payload, as_json=False)

    def test_notification_failure_does_not_block_other_channels(self):
        tr = tracker.Tracker()
        tr.start("job")
        payload = tr.stop(callbacks=[FailingCallback(), SucceedingCallback()])
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["notifications"]["email"]["status"], "failed")
        self.assertEqual(payload["notifications"]["text"]["status"], "sent")

    def test_database_round_trip_and_parameterized_session_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = os.path.join(directory, "jort.db")
            with patch.object(config, "JORT_DIR", directory), \
                 patch.object(config, "CONFIG_PATH", os.path.join(directory, "config")), \
                 patch.object(config, "_get_data_dir", return_value=directory), \
                 patch.object(config, "_get_database_path", return_value=database_path):
                config._initialize_db()
                payload = {
                    "job_id": "job-1",
                    "session_id": "session-1",
                    "name": "quoted ' command",
                    "status": "success",
                    "machine": "test",
                    "date_created": "2026-01-01T00:00:00+00:00",
                    "date_modified": "2026-01-01T00:00:01+00:00",
                    "runtime": 1.0,
                    "stdout_fn": None,
                    "error_message": None,
                    "exit_code": 0,
                    "argv": ["quoted", "command"],
                    "metadata": {},
                    "notification_channels": [],
                    "notifications": {},
                }
                with contextlib.closing(database._connect()) as connection:
                    connection.execute(
                        "INSERT INTO sessions(session_id, session_name) VALUES(?, ?)",
                        ("session-1", "quoted ' session"),
                    )
                    connection.commit()
                database.save_job(payload)
                self.assertEqual(database.get_job("job-1")["name"], "quoted ' command")
                self.assertEqual(
                    database.list_jobs(session="quoted ' session")[0]["job_name"],
                    "quoted ' command",
                )


if __name__ == "__main__":
    unittest.main()
