import os
import pandas as pd
import sqlite3
import contextlib
import click

from . import config
from . import exceptions


def print_jobs(session=None, tail=None, full_details=False):
    try:
        with contextlib.closing(sqlite3.connect(config._get_database_path())) as con:
            cur = con.cursor()
            if not full_details:
                sql = (
                    "SELECT jobs.job_name, sessions.session_name, jobs.status, "
                    "jobs.machine, jobs.date_created, jobs.date_finished, "
                    "jobs.runtime, jobs.error_message "
                    "FROM jobs JOIN sessions "
                    "ON jobs.session_id = sessions.session_id"
                )
                if session is not None:
                    sql += f" AND sessions.session_name = '{session}'"
            else:
                sql = (
                    "SELECT jobs.* from jobs"
                )
                if session is not None:
                    sql += f" JOIN sessions ON jobs.session_id = sessions.session_id AND sessions.session_name = '{session}'"

            df = pd.read_sql(sql, con)
            if session is not None and len(df) == 0:
                raise ValueError(f"No jobs found with session `{session}`")
            if tail is not None:
                df = df.tail(tail)
            return df
    except sqlite3.OperationalError as e:
        raise exceptions.JortException("Missing database - make sure to initialize with `jort.init()` or `jort init`") from e
    

@click.command(options_metavar='[<options>]')
@click.option('-s', '--session', type=str,
              help='filter by session name')
@click.option('-r', '--rows', type=int,
              help='number of rows to print')
@click.option('-f', '--full-details', is_flag=True,
              help='show all details, including ids')
def inspect(session, rows, full_details):
    """
    Get saved job details from database
    """
    print(print_jobs(session=session, tail=rows, full_details=full_details))
