import os
import json
import twilio.rest
import humanfriendly
from . import config


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
            f'The job \'{payload["short_name"]}\' finished running '
            f'in {humanfriendly.format_timespan(payload["runtime"])}'
        )

    def execute(self, payload):
        print(self.format_message(payload))


class SMSNotification(Callback):
    def __init__(self, receive_number=None):
        self.receive_number = receive_number
        if receive_number is None:
            with open(f"{config.JORT_DIR}/config", "r") as f:
                config_data = json.load(f)
                self.receive_number = config_data["twilio_receive_number"]
                self.send_number = config_data["twilio_send_number"]
                self.twilio_account_sid = config_data["twilio_account_sid"]
                self.twilio_auth_token = config_data["twilio_auth_token"]

    def format_message(self, payload):
        if payload["status"] == "success":
            return (
                f'Your job \'{payload["short_name"]}\' successfully completed '
                f'in {humanfriendly.format_timespan(payload["runtime"])}'
            )
        elif payload["status"] == "error":
            error_name = payload["error_message"].split(":")[0]
            return (
                f'Your job \'{payload["short_name"]}\' exited in error ({error_name}) '
                f'after {humanfriendly.format_timespan(payload["runtime"])}'
            )
        else:
            return (
                f'Your job \'{payload["short_name"]}\' finished running '
                f'in {humanfriendly.format_timespan(payload["runtime"])}'
            )
        
    
    def execute(self, payload):
        client = twilio.rest.Client(self.twilio_account_sid,
                                    self.twilio_auth_token)
        message = client.messages.create(body=self.format_message(payload),
                                         from_=self.send_number,
                                         to=self.receive_number)


class EmailNotification(Callback):
    def __init__(self, email=None):
        self.email = email
        if email is None:
            with open(f"{config.JORT_DIR}/config", "r") as f:
                config_data = json.load(f)
                self.email = config_data["email"]

    def format_message(self, payload):
        return ""

    def execute(self, payload):
        pass


