"""
Initialize jort directories with correct permissions.
"""

import os
import json
import sqlite3
import contextlib
import psutil
import click
import socket
from pathlib import Path

from . import exceptions

# Create internal jort directory
JORT_DIR = os.path.join(os.path.expanduser('~'), ".jort")
CONFIG_PATH = os.path.join(JORT_DIR, "config")


class OrderedGroup(click.Group):
    def __init__(self, name=None, commands=None, **attrs):
        super(OrderedGroup, self).__init__(name, commands, **attrs)
        self.commands = commands or {}

    def list_commands(self, ctx):
        return self.commands


def init_internal_config():
    Path(JORT_DIR).mkdir(mode=0o700, parents=True, exist_ok=True)
    Path(CONFIG_PATH).touch(mode=0o600, exist_ok=True)


def init_database():
    if not _check_data_dir_nfs():
        Path(_get_data_dir()).mkdir(mode=0o700, parents=True, exist_ok=True)
        _initialize_db()
    else:
        click.echo("Database not initialized; path is NFS mounted - use `jort.config_general()` or `jort config general` to change location")


@click.command(name="init")
def init():
    """
    Initialize internal jort directory and config file
    """
    init_internal_config()
    init_database()


def _get_config_data():
    try:
        with open(CONFIG_PATH, "r") as f:
            try:
                config_data = json.load(f)
            except json.decoder.JSONDecodeError:
                config_data = {}
    except FileNotFoundError as e:
        config_data = {}
    return config_data


@click.group(name='config',
             chain=True, 
             options_metavar='[-h]', 
             subcommand_metavar='<command> [<args>] [<command2> [<args>]]...',
             cls=OrderedGroup)
def config_group():
    """
    Configure user details and auth for notifications
    """
    init_internal_config()


@click.command(name='general', options_metavar='[<options>]')
@click.option("--machine", prompt="Machine name", 
              default=lambda: _get_config_data().get("machine", socket.gethostname()),
              show_default=_get_config_data().get("machine", socket.gethostname()))
@click.option("--data-dir", prompt="Location for storing jort data (parent directory)", 
              default=lambda: _get_config_data().get("data_dir", os.path.expanduser("~")),
              show_default=_get_config_data().get("data_dir", os.path.expanduser("~")))
def config_general(machine, data_dir):
    """
    Configure general details
    """
    config_data = _get_config_data()
    if machine != "":
        config_data["machine"] = machine
    if data_dir != "":
        config_data["data_dir"] = data_dir
        jort_data_dir = os.path.join(data_dir, ".jort")
        Path(jort_data_dir).mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config_data, f)
    if data_dir != "":
        init_database()


@click.command(name='email', options_metavar='[<options>]')
@click.option("--email", prompt=True, 
              default=lambda: _get_config_data().get("email", ""),
              show_default=_get_config_data().get("email"))
@click.option("--email-password", prompt=True, hide_input=True,
              default=lambda: "*"*8 if _get_config_data().get("email_password") is not None else "",
              show_default="*"*8 if _get_config_data().get("email_password") is not None else None)
@click.option("--smtp-server", prompt="SMTP server", 
              default=lambda: _get_config_data().get("smtp_server", ""),
              show_default=_get_config_data().get("smtp_server"))
def config_email(email, email_password, smtp_server):
    """
    Configure e-mail authentication
    """
    config_data = _get_config_data()
    if email != "":
        config_data["email"] = email
    if email_password not in ["", "*"*8]:
        config_data["email_password"] = email_password
    if smtp_server != "":
        config_data["smtp_server"] = smtp_server
    with open(CONFIG_PATH, "w") as f:
        json.dump(config_data, f)


@click.command(name='text', options_metavar='[<options>]')
@click.option("--twilio-receive-number", prompt=True, 
              default=lambda: _get_config_data().get("twilio_receive_number", ""),
              show_default=_get_config_data().get("twilio_receive_number"))
@click.option("--twilio-send-number", prompt=True, 
              default=lambda: _get_config_data().get("twilio_send_number", ""),
              show_default=_get_config_data().get("twilio_send_number"))
@click.option("--twilio-account-sid", prompt=True, 
              default=lambda: _get_config_data().get("twilio_account_sid", ""),
              show_default=_get_config_data().get("twilio_account_sid"))
@click.option("--twilio-auth-token", prompt=True, hide_input=True,
              default=lambda: "*"*8 if _get_config_data().get("twilio_auth_token") is not None else "",
              show_default="*"*8 if _get_config_data().get("twilio_auth_token") is not None else None)
def config_text(twilio_receive_number, twilio_send_number, twilio_account_sid, twilio_auth_token):
    """
    Configure SMS text authentication
    """
    config_data = _get_config_data()
    if twilio_receive_number != "":
        config_data["twilio_receive_number"] = twilio_receive_number
    if twilio_send_number != "":
        config_data["twilio_send_number"] = twilio_send_number
    if twilio_account_sid != "":
        config_data["twilio_account_sid"] = twilio_account_sid
    if twilio_auth_token not in ["", "*"*8]:
        config_data["twilio_auth_token"] = twilio_auth_token
    with open(CONFIG_PATH, "w") as f:
        json.dump(config_data, f)


@click.command(name='all', options_metavar='[<options>]')
@click.option("--machine", prompt="Machine name", 
              default=lambda: _get_config_data().get("machine", socket.gethostname()),
              show_default=_get_config_data().get("machine", socket.gethostname()))
@click.option("--data-dir", prompt="Location for storing jort data", 
              default=lambda: _get_config_data().get("data_dir", os.path.expanduser("~")),
              show_default=_get_config_data().get("data_dir", os.path.expanduser("~")))
@click.option("--twilio-receive-number", prompt=True, 
              default=lambda: _get_config_data().get("twilio_receive_number", ""),
              show_default=_get_config_data().get("twilio_receive_number"))
@click.option("--twilio-send-number", prompt=True, 
              default=lambda: _get_config_data().get("twilio_send_number", ""),
              show_default=_get_config_data().get("twilio_send_number"))
@click.option("--twilio-account-sid", prompt=True, 
              default=lambda: _get_config_data().get("twilio_account_sid", ""),
              show_default=_get_config_data().get("twilio_account_sid"))
@click.option("--twilio-auth-token", prompt=True, hide_input=True,
              default=lambda: "*"*8 if _get_config_data().get("twilio_auth_token") is not None else "",
              show_default="*"*8 if _get_config_data().get("twilio_auth_token") is not None else None)
@click.option("--email", prompt=True, 
              default=lambda: _get_config_data().get("email", ""),
              show_default=_get_config_data().get("email"))
@click.option("--email-password", prompt=True, hide_input=True,
              default=lambda: "*"*8 if _get_config_data().get("email_password") is not None else "",
              show_default="*"*8 if _get_config_data().get("email_password") is not None else None)
@click.option("--smtp-server", prompt="SMTP server", 
              default=lambda: _get_config_data().get("smtp_server", ""),
              show_default=_get_config_data().get("smtp_server"))
@click.pass_context
def config_all(ctx, machine, data_dir, 
               email, email_password, smtp_server, 
               twilio_receive_number, twilio_send_number, twilio_account_sid, twilio_auth_token):
    """
    Go through full configuration menu
    """
    ctx.invoke(config_general, 
               machine=machine, 
               data_dir=data_dir)
    ctx.invoke(config_email, 
               email=email, 
               email_password=email_password, 
               smtp_server=smtp_server)
    ctx.invoke(config_text, 
               twilio_receive_number=twilio_receive_number, 
               twilio_send_number=twilio_send_number, 
               twilio_account_sid=twilio_account_sid, 
               twilio_auth_token=twilio_auth_token)


config_group.add_command(config_general)
config_group.add_command(config_email)
config_group.add_command(config_text)
config_group.add_command(config_all)


def _find_mountpoint(path):
    """
    Find mountpoint on machine.
    """
    path = os.path.realpath(path)
    while not os.path.ismount(path):
        path = os.path.dirname(path)
    return path


def _check_nfs(path="."):
    """
    Check whether the disk mount is NFS. 
    """
    mountpoint = _find_mountpoint(path)
    for p in psutil.disk_partitions(all=True):
        if p.mountpoint == mountpoint:
            return "nfs" in p.fstype
    raise OSError("Did not match partition! Something's wrong...")


def _check_data_dir_nfs():
    """
    Check whether the parent of the data directory is on NFS. 
    """
    jort_data_parent_dir = _get_config_data().get("data_dir", os.path.expanduser('~'))
    return _check_nfs(jort_data_parent_dir)


def _get_data_dir():
    """
    Read data directory from config, failing if it's on an NFS mount from SQLite locks.
    """
    jort_data_parent_dir = _get_config_data().get("data_dir", os.path.expanduser('~'))
    if _check_nfs(jort_data_parent_dir):
        raise exceptions.JortException("Cannot initialize database on NFS mount, please enter target data directory with `jort config general`")
    else:
        jort_data_dir = os.path.join(jort_data_parent_dir, ".jort")
    return jort_data_dir


def _get_database_path():
    """
    Get database path from config, failing if it's on an NFS mount from SQLite locks.
    """
    return os.path.join(_get_data_dir(), "jort.db")


# Set up database
def _initialize_db():
    """
    Populate database sessions and jobs tables if they
    don't exist already.
    """
    with contextlib.closing(sqlite3.connect(_get_database_path())) as con:
        cur = con.cursor()

        sql = (
            "CREATE TABLE IF NOT EXISTS sessions ("
                "session_id TEXT PRIMARY KEY,"
                "session_name TEXT"
            ")"
        )
        cur.execute(sql)

        sql = (
            "CREATE TABLE IF NOT EXISTS jobs ("
            "    job_id TEXT PRIMARY KEY,"
            "    session_id TEXT,"
            "    job_name TEXT,"
            "    status TEXT,"
            "    machine TEXT,"
            "    date_created TEXT,"
            "    date_finished TEXT,"
            "    runtime REAL,"
            "    stdout_fn TEXT,"
            "    error_message TEXT,"
            "    FOREIGN KEY(session_id) REFERENCES sessions(session_id)"
            ")"
        )
        cur.execute(sql)

        con.commit()

