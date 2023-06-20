"""
Initialize jort directories with correct permissions.
"""

import os
import json
import sqlite3
from pathlib import Path


# Create internal jort directory
JORT_DIR = f"{os.path.expanduser('~')}/.jort"
Path(f"{JORT_DIR}/").mkdir(mode=0o700, parents=True, exist_ok=True)
Path(f"{JORT_DIR}/config").touch(mode=0o600, exist_ok=True)

def get_config_data():
    with open(f"{JORT_DIR}/config", "r") as f:
        try:
            config_data = json.load(f)
        except json.decoder.JSONDecodeError:
            config_data = {}
    return config_data

# Set up database
def _initialize_db():
    con = sqlite3.connect(f"{JORT_DIR}/jort.db")
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
    con.close()

_initialize_db()