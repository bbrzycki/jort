"""Regression tests for email notification presentation."""

import unittest

from jort.reporting_callbacks import EmailNotification
from jort.exceptions import JortException


class EmailNotificationTests(unittest.TestCase):
    def setUp(self):
        # Formatting does not require credentials; avoid coupling these tests
        # to the user's local notification configuration.
        self.notification = EmailNotification.__new__(EmailNotification)

    def payload(self, **overrides):
        payload = {
            "name": "benchmark --size small",
            "status": "success",
            "machine": "worker-1",
            "date_modified": "2026-08-21T12:34:56",
            "runtime": 12.5,
            "stdout_fn": None,
            "error_message": None,
        }
        payload.update(overrides)
        return payload

    def test_success_email_has_structured_summary(self):
        message = self.notification.format_message(self.payload())

        self.assertEqual(message["subject"],
                         "[jort] Completed: benchmark --size small")
        self.assertIn("Status:   Completed", message["body"])
        self.assertIn("Runtime:  12.5 seconds", message["body"])
        self.assertIn("JORT / JOB NOTIFICATION", message["html_body"])
        self.assertIn("worker-1", message["html_body"])
        self.assertIn("Completed", message["html_body"])

    def test_error_details_are_escaped_and_compact(self):
        message = self.notification.format_message(self.payload(
            name="build <nightly>",
            status="error",
            error_message="ValueError: <bad input>",
        ))

        self.assertEqual(message["subject"], "[jort] Failed: build <nightly>")
        self.assertIn("ValueError: &lt;bad input&gt;", message["html_body"])
        self.assertIn("build &lt;nightly&gt;", message["html_body"])
        self.assertNotIn("<bad input>", message["html_body"])

    def test_output_attachment_is_called_out(self):
        message = self.notification.format_message(self.payload(
            stdout_fn="output.txt",
        ))

        self.assertIn("output.txt", message["body"])
        self.assertIn("output.txt", message["html_body"])

    def test_unknown_status_is_rejected(self):
        with self.assertRaises(JortException):
            self.notification.format_message(self.payload(status="running"))


if __name__ == "__main__":
    unittest.main()
