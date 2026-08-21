"""Regression tests for Jort's documented public interfaces."""

import inspect
import unittest
from unittest.mock import patch

from click.testing import CliRunner

import jort
from jort import jort_exe
from jort import reporting_callbacks
from jort import track_cli


class PublicApiContractTests(unittest.TestCase):
    def test_top_level_exports_existing_command_and_notifications(self):
        self.assertIs(jort.track_new, track_cli.track_new)
        self.assertIs(jort.EmailNotification,
                      reporting_callbacks.EmailNotification)
        self.assertIs(jort.TextNotification,
                      reporting_callbacks.TextNotification)

    def test_track_new_keeps_independent_notification_options(self):
        parameters = inspect.signature(jort.track_new).parameters
        self.assertIn("send_email", parameters)
        self.assertIn("send_text", parameters)
        self.assertFalse(parameters["send_email"].default)
        self.assertFalse(parameters["send_text"].default)

    def test_callback_builder_supports_each_channel_combination(self):
        for send_email, send_text in (
            (False, False),
            (True, False),
            (False, True),
            (True, True),
        ):
            with self.subTest(send_email=send_email, send_text=send_text):
                with patch.object(reporting_callbacks, "PrintReport") as print_report, \
                     patch.object(reporting_callbacks, "EmailNotification") as email, \
                     patch.object(reporting_callbacks, "TextNotification") as text:
                    callbacks = track_cli._notification_callbacks(
                        send_email=send_email,
                        send_text=send_text,
                    )

                print_report.assert_called_once_with()
                if send_email:
                    email.assert_called_once_with()
                else:
                    email.assert_not_called()
                if send_text:
                    text.assert_called_once_with()
                else:
                    text.assert_not_called()

                expected = [print_report.return_value]
                if send_email:
                    expected.append(email.return_value)
                if send_text:
                    expected.append(text.return_value)
                self.assertEqual(callbacks, expected)

    def test_cli_forwards_both_notification_flags(self):
        runner = CliRunner()
        with patch.object(jort_exe.track_cli, "track_new") as track_new:
            result = runner.invoke(
                jort_exe.cli,
                ["track", "--email", "--text", "echo hello"],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        track_new.assert_called_once_with(
            "echo hello",
            use_shell=False,
            store_stdout=False,
            save_filename=None,
            to_db=False,
            session_name=None,
            unique=False,
            send_text=True,
            send_email=True,
            verbose=False,
        )


if __name__ == "__main__":
    unittest.main()
