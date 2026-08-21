from abc import ABC, abstractmethod
import os
import json
import smtplib
import ssl
import email
from html import escape as html_escape
from email import encoders
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import twilio.rest
import humanfriendly
from . import config
from . import exceptions


class Callback(ABC):
    """
    Abstract base class for notification callbacks.
    """
    def __init__(self):
        pass

    @abstractmethod
    def format_message(self, payload):
        """
        Format notification message as a string.
        """
        pass

    @abstractmethod
    def execute(self, payload):
        """
        Send notification given job status payload.
        """
        pass
    
    
class PrintReport(Callback):
    """
    Print job runtime on completion.
    """
    def __init__(self):
        pass

    def format_message(self, payload):
        if payload["status"] == "success":
            return (
                f'\n'
                f'Your job `{payload["name"]}` successfully completed '
                f'in {humanfriendly.format_timespan(payload["runtime"])}'
            )
        elif payload["status"] == "error":
            error_text = payload["error_message"].split(":")[0]
            return (
                f'\n'
                f'Your job `{payload["name"]}` exited in error ({error_text}) '
                f'after {humanfriendly.format_timespan(payload["runtime"])}'
            )
        elif payload["status"] == "finished":
            return (
                f'\n'
                f'Your job `{payload["name"]}` finished running '
                f'in {humanfriendly.format_timespan(payload["runtime"])}'
            )
        else:
            raise exceptions.JortException(f'Invalid status: {payload["status"]}')

    def execute(self, payload):
        print(self.format_message(payload))


class EmailNotification(Callback):
    """
    Send email notifications to and from your email account. Requires login 
    credentials, which can be entered at the command line via :code:`jort config`.
    """
    def __init__(self, email=None):
        config_data = config._get_config_data()
        self.email = config_data.get("email")
        if email is not None:
            self.email = email
        self.email_password = config_data.get("email_password")
        self.smtp_server = config_data.get("smtp_server")

        if self.email_password is None:
            raise exceptions.JortCredentialException("Missing email password, add with `jort config email` command")
        if self.smtp_server is None:
            raise exceptions.JortException("Missing SMTP server, add with `jort config email` command")
        if self.email is None:
            raise exceptions.JortException("Missing email")

    def format_message(self, payload):
        status = payload["status"]
        status_details = {
            "success": {
                "label": "Completed",
                "headline": "Your job completed successfully",
                "subject": "Completed",
                "color": "#067647",
                "background": "#ecfdf3",
            },
            "error": {
                "label": "Failed",
                "headline": "Your job exited with an error",
                "subject": "Failed",
                "color": "#b42318",
                "background": "#fef3f2",
            },
            "finished": {
                "label": "Finished",
                "headline": "Your job finished running",
                "subject": "Finished",
                "color": "#175cd3",
                "background": "#eff8ff",
            },
        }
        if status not in status_details:
            raise exceptions.JortException(f'Invalid status: {status}')

        details = status_details[status]
        job_name = str(payload.get("name", "Unnamed job"))
        date_modified = str(payload.get("date_modified", "Unknown"))
        runtime = humanfriendly.format_timespan(payload["runtime"])
        machine = payload.get("machine")
        machine_text = str(machine) if machine is not None else None
        error_text = self._compact_error(payload.get("error_message"))

        subject_job = " ".join(job_name.split())
        if len(subject_job) > 90:
            subject_job = f"{subject_job[:87]}..."
        subject = f'[jort] {details["subject"]}: {subject_job}'

        # Keep the plain-text alternative useful for clients that do not render
        # HTML, while preserving multiline shell commands in a readable block.
        indented_job = job_name.replace("\n", "\n    ")
        body_lines = [
            "JORT / JOB NOTIFICATION",
            "",
            details["headline"],
            "",
            f"Job:      {indented_job}",
            f"Status:   {details['label']}",
            f"Runtime:  {runtime}",
            f"Finished: {date_modified} (UTC)",
        ]
        if machine_text is not None:
            body_lines.append(f"Machine:  {machine_text}")
        if error_text is not None:
            body_lines.extend(["", f"Error: {error_text}"])
        if payload.get("stdout_fn") is not None:
            body_lines.extend(["", "Full command output is attached as output.txt."])
        body_lines.extend(["", "--", "jort"])
        body = "\r\n".join(body_lines)

        html_job = html_escape(job_name).replace("\n", "<br>")
        html_date = html_escape(date_modified)
        html_runtime = html_escape(runtime)
        html_machine = html_escape(machine_text) if machine_text is not None else None
        html_error = html_escape(error_text) if error_text is not None else None
        machine_row = ""
        if html_machine is not None:
            machine_row = (
                f'<tr><td style="padding:7px 0;color:#667085;">Machine</td>'
                f'<td style="padding:7px 0;text-align:right;">{html_machine}</td></tr>'
            )
        error_block = ""
        if html_error is not None:
            error_block = (
                f'<div style="margin-top:20px;padding:12px 14px;'
                f'border-left:4px solid #d92d20;background:#fef3f2;">'
                f'<div style="font-size:12px;font-weight:700;color:#b42318;'
                f'text-transform:uppercase;letter-spacing:.04em;">Error</div>'
                f'<div style="margin-top:4px;color:#7a271a;word-break:break-word;">'
                f'{html_error}</div></div>'
            )
        attachment_note = ""
        if payload.get("stdout_fn") is not None:
            attachment_note = (
                '<p style="margin:20px 0 0;color:#667085;font-size:13px;">'
                'Full command output is attached as <strong>output.txt</strong>.</p>'
            )

        html_body = (
            '<!doctype html>'
            '<html><head><meta charset="utf-8"></head>'
            '<body style="margin:0;background:#f2f4f7;color:#101828;'
            'font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;">'
            '<div style="padding:28px 14px;">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0">'
            '<tr><td align="center">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            'style="max-width:600px;background:#ffffff;border:1px solid #eaecf0;'
            'border-radius:12px;overflow:hidden;">'
            '<tr><td style="padding:20px 24px;background:#101828;color:#ffffff;">'
            '<div style="font-size:11px;font-weight:700;letter-spacing:.12em;'
            'color:#98a2b3;">JORT / JOB NOTIFICATION</div>'
            f'<div style="margin-top:8px;font-size:22px;font-weight:650;">'
            f'{details["headline"]}</div></td></tr>'
            '<tr><td style="padding:24px;">'
            f'<span style="display:inline-block;padding:5px 10px;border-radius:999px;'
            f'background:{details["background"]};color:{details["color"]};'
            f'font-size:12px;font-weight:700;">{details["label"]}</span>'
            f'<div style="margin-top:16px;padding:12px 14px;background:#f8fafc;'
            'border:1px solid #eaecf0;border-radius:8px;font-family:ui-monospace, '
            'SFMono-Regular, Menlo, monospace;font-size:13px;line-height:1.5;'
            f'word-break:break-word;">{html_job}</div>'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            'style="margin-top:18px;border-collapse:collapse;font-size:14px;">'
            f'<tr><td style="padding:7px 0;color:#667085;">Status</td>'
            f'<td style="padding:7px 0;text-align:right;font-weight:600;">'
            f'{details["label"]}</td></tr>'
            f'<tr><td style="padding:7px 0;color:#667085;">Runtime</td>'
            f'<td style="padding:7px 0;text-align:right;font-weight:600;">'
            f'{html_runtime}</td></tr>'
            f'<tr><td style="padding:7px 0;color:#667085;">Finished</td>'
            f'<td style="padding:7px 0;text-align:right;">{html_date} UTC</td></tr>'
            f'{machine_row}'
            '</table>'
            f'{error_block}{attachment_note}'
            '</td></tr>'
            '<tr><td style="padding:16px 24px;border-top:1px solid #eaecf0;'
            'color:#98a2b3;font-size:12px;">Jort · local job notification</td></tr>'
            '</table></td></tr></table></div></body></html>'
        )
        email_data = {
            "subject": subject,
            "body": body,
            "html_body": html_body,
        }
        return email_data

    @staticmethod
    def _compact_error(error_message):
        """Return a concise, single-line error suitable for an email."""
        if error_message is None:
            return None
        error_text = " ".join(str(error_message).split())
        if len(error_text) > 500:
            return f"{error_text[:497]}..."
        return error_text

    def execute(self, payload):
        email_data = self.format_message(payload)

        message = MIMEMultipart("alternative")
        message.attach(MIMEText(email_data["body"], "plain"))
        message.attach(MIMEText(email_data["html_body"], "html"))

        if payload["stdout_fn"] is not None:
            stdout_path = os.path.join(config._get_data_dir(), payload["stdout_fn"])
            with open(stdout_path, "r") as f:
                attachment = MIMEApplication(f.read(), _subtype="txt")
            attachment.add_header("Content-Disposition", "attachment", filename="output.txt")

            message_mix = MIMEMultipart("mixed")
            message_mix.attach(message)
            message_mix.attach(attachment)
            message = message_mix

        message["Subject"] = email_data["subject"]
        message["From"] = self.email
        message["To"] = self.email

        # Secure connection
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(self.smtp_server, port=465, context=context) as server:
            server.login(self.email, self.email_password)
            server.sendmail(message["From"], message["To"], message.as_string())


class TextNotification(Callback):
    """
    Send SMS notifications to and from numbers managed by your Twilio account. Requires 
    Twilio credentials, which can be entered at the command line via :code:`jort config`.
    """
    def __init__(self, receive_number=None):
        config_data = config._get_config_data()
        self.receive_number = config_data.get("twilio_receive_number")
        if receive_number is not None:
            self.receive_number = receive_number
        self.send_number = config_data.get("twilio_send_number")
        self.twilio_account_sid = config_data.get("twilio_account_sid")
        self.twilio_auth_token = config_data.get("twilio_auth_token")

        if self.twilio_account_sid is None or self.twilio_auth_token is None:
            raise exceptions.JortCredentialException("Missing Twilio credentials, add with `jort config text` command")
        if self.send_number is None:
            raise exceptions.JortException("Missing Twilio sending number, add with `jort config text` command")
        if self.receive_number is None:
            raise exceptions.JortException("Missing receiving number")

    def format_message(self, payload):
        if payload["status"] == "success":
            return (
                f'Your job `{payload["name"]}` successfully completed '
                f'in {humanfriendly.format_timespan(payload["runtime"])}'
            )
        elif payload["status"] == "error":
            error_text = payload["error_message"].split(":")[0]
            return (
                f'Your job `{payload["name"]}` exited in error ({error_text}) '
                f'after {humanfriendly.format_timespan(payload["runtime"])}'
            )
        elif payload["status"] == "finished":
            return (
                f'Your job `{payload["name"]}` finished running '
                f'in {humanfriendly.format_timespan(payload["runtime"])}'
            )
        else:
            raise exceptions.JortException(f'Invalid status: {payload["status"]}')
    
    def execute(self, payload):
        client = twilio.rest.Client(self.twilio_account_sid,
                                    self.twilio_auth_token)
        message = client.messages.create(body=self.format_message(payload),
                                         from_=self.send_number,
                                         to=self.receive_number)
