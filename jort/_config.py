"""
Initialize jort directories with correct permissions.
"""

import os
import json
import sqlite3
import contextlib
import psutil
from pathlib import Path

from . import exceptions

# Create internal jort directory
JORT_DIR = os.path.join(os.path.expanduser('~'), ".jort")
Path(f"{JORT_DIR}").mkdir(mode=0o700, parents=True, exist_ok=True)
CONFIG_PATH = os.path.join(JORT_DIR, "config")
Path(CONFIG_PATH).touch(mode=0o600, exist_ok=True)

def get_config_data():
    with open(CONFIG_PATH, "r") as f:
        try:
            config_data = json.load(f)
        except json.decoder.JSONDecodeError:
            config_data = {}
    return config_data

def _find_mountpoint(path):
    path = os.path.realpath(path)
    while not os.path.ismount(path):
        path = os.path.dirname(path)
    return path

def _check_nfs_home():
    mountpoint = _find_mountpoint(".")
    for p in psutil.disk_partitions(all=True):
        if p.mountpoint == mountpoint:
            return "nfs" in p.fstype
    raise OSError("Did not match partition! Something's wrong...")


# Set up database
def _initialize_db():
    jort_data_dir = get_config_data().get("data_directory")
    if jort_data_dir is None:
        if _check_nfs_home():
            raise exceptions.JortException("Cannot initialize database, please entire with `jort config`")
        else:
            jort_data_dir = JORT_DIR

    jort_db = os.path.join(jort_data_dir, "jort.db")
    with contextlib.closing(sqlite3.connect(jort_db)) as con:
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

if not _check_nfs_home():
    _initialize_db()