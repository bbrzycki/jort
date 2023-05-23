import os
import json
import smtplib
import ssl
import email
from email import encoders
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import twilio.rest
import humanfriendly
from . import config
from . import exceptions


class Callback(object):
    def __init__(self):
        pass

    def format_message(self, payload):
        pass

    def execute(self, payload):
        pass
    
    
class PrintReport(Callback):
    def __init__(self):
        pass

    def format_message(self, payload):
        return (
            f'\n'
            f'The job \'{payload["name"]}\' finished running '
            f'in {humanfriendly.format_timespan(payload["runtime"])}'
        )

    def execute(self, payload):
        print(self.format_message(payload))


class SMSNotification(Callback):
    """
    Send SMS notifications to and from numbers managed by your Twilio account.
    """
    def __init__(self, receive_number=None):
        config_data = config.get_config_data()
        self.receive_number = config_data.get("twilio_receive_number")
        self.send_number = config_data.get("twilio_send_number")
        self.twilio_account_sid = config_data.get("twilio_account_sid")
        self.twilio_auth_token = config_data.get("twilio_auth_token")
        if receive_number is not None:
            self.receive_number = receive_number

        if self.twilio_account_sid is None or self.twilio_auth_token is None:
            raise exceptions.JortCredentialException("Missing Twilio credentials, add with `jort -i` command")
        if self.send_number is None:
            raise exceptions.JortException("Missing Twilio sending number, add with `jort -i` command")
        if self.receive_number is None:
            raise exceptions.JortException("Missing receiving number")

    def format_message(self, payload):
        if payload["status"] == "success":
            return (
                f'Your job \'{payload["name"]}\' successfully completed '
                f'in {humanfriendly.format_timespan(payload["runtime"])}'
            )
        elif payload["status"] == "error":
            error_text = payload["error_message"].split(":")[0]
            return (
                f'Your job \'{payload["name"]}\' exited in error ({error_text}) '
                f'after {humanfriendly.format_timespan(payload["runtime"])}'
            )
        elif payload["status"] == "finished":
            return (
                f'Your job \'{payload["name"]}\' finished running '
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


class EmailNotification(Callback):
    """
    Send email notifications to and from your email account.
    """
    def __init__(self, email=None):
        config_data = config.get_config_data()
        self.email = config_data.get("email")
        self.smtp_server = config_data.get("smtp_server")
        self.email_password = config_data.get("email_password")
        if email is not None:
            self.email = email

        if self.email_password is None:
            raise exceptions.JortCredentialException("Missing email password, add with `jort -i` command")
        if self.smtp_server is None:
            raise exceptions.JortException("Missing SMTP server, add with `jort -i` command")
        if self.email is None:
            raise exceptions.JortException("Missing email")

    def format_message(self, payload):
        if payload["machine"] is not None:
            machine_text = f' on machine {payload["machine"]}'
            html_machine_text = f' on machine <strong>{payload["machine"]}</strong>'
        else:
            machine_text = ''
            html_machine_text = ''

        if payload["status"] == "success":
            subject = "[jort] Your job finished successfully!"

            summary_text = (
                f'Your job `{payload["name"]}` completed at {payload["date_modified"]} (UTC)'
                f'{machine_text} with no errors.'
            )
            html_summary_text = (
                f'Your job <strong>{payload["name"]}</strong> completed at <strong>{payload["date_modified"]}</strong> (UTC)'
                f'{html_machine_text} with no errors.'
            )
        elif payload["status"] == "error":
            subject = "[jort] Your job exited with an error"

            error_text = payload["error_message"].split(":")[0]

            summary_text = (
                f'Your job `{payload["name"]}` exited at {payload["date_modified"]} (UTC)'
                f'{machine_text} with error `{error_text}`.'
            )
            html_summary_text = (
                f'Your job <strong>{payload["name"]}</strong> exited at <strong>{payload["date_modified"]}</strong> (UTC)'
                f'{html_machine_text} with error <strong>{error_text}</strong>.'
            )
        elif payload["status"] == "finished":
            subject = "[jort] Your job has finished!"

            summary_text = (
                f'Your job `{payload["name"]}` finished running at {payload["date_modified"]} (UTC)'
                f'{machine_text}.'
            )
            html_summary_text = (
                f'Your job <strong>{payload["name"]}</strong> finished running at <strong>{payload["date_modified"]}</strong> (UTC)'
                f'{html_machine_text}.'
            )
        else:
            raise exceptions.JortException(f'Invalid status: {payload["status"]}')
        
        runtime_text = f'The job\'s total runtime was {humanfriendly.format_timespan(payload["runtime"])}.'
        html_runtime_text = f'The job\'s total runtime was <strong>{humanfriendly.format_timespan(payload["runtime"])}</strong>.'

        body = (
            f'{summary_text}\r\n'
            f'{runtime_text}\r\n'
            f'--\r\n'
            f'jort'
        )
        html_body = (
            f'<html>'
            f'<head></head>'
            f'<body>'
            f'  <p>{html_summary_text}</p>'
            f'  <p>{html_runtime_text}</p>'
            f'  <p>--<br>jort</p>'
            f'</body>'
            f'</html>'
        )
        email_data = {
            "subject": subject,
            "body": body,
            "html_body": html_body,
        }
        return email_data

    def execute(self, payload):
        email_data = self.format_message(payload)

        message = MIMEMultipart("alternative")
        message.attach(MIMEText(email_data["body"], "plain"))
        message.attach(MIMEText(email_data["html_body"], "html"))

        if payload["stdout_fn"] is not None:
            stdout_path = f'{config.JORT_DIR}/{payload["stdout_fn"]}'
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

            




