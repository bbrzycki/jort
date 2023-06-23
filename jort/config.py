"""
Initialize jort directories with correct permissions.
"""

import os
import json
import sqlite3
import contextlib
import psutil
import click
from pathlib import Path

from . import exceptions

# Create internal jort directory
JORT_DIR = os.path.join(os.path.expanduser('~'), ".jort")
CONFIG_PATH = os.path.join(JORT_DIR, "config")


@click.command(name="init")
def init():
    """
    Initialize internal jort directory and config file
    """
    Path(JORT_DIR).mkdir(mode=0o700, parents=True, exist_ok=True)
    Path(CONFIG_PATH).touch(mode=0o600, exist_ok=True)
    if not _check_data_dir_nfs():
        _initialize_db(_get_data_dir())
    else:
        click.echo("Database not initialized; path is NFS mounted - use `jort config general` to change location")


def _get_config_data():
    try:
        with open(CONFIG_PATH, "r") as f:
            try:
                config_data = json.load(f)
            except json.decoder.JSONDecodeError:
                config_data = {}
        return config_data
    except FileNotFoundError as e:
        raise exceptions.JortException("Missing config - make sure to initialize with `jort.init()` or `jort init`") from e


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
def _initialize_db(jort_data_dir):
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

