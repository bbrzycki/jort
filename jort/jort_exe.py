#!/usr/bin/env python3
import os
import errno
import socket
import json
import getpass
import argparse
import click
from pathlib import Path

from . import config
from . import track_cli
from . import database
from ._version import __version__


config_data = config._get_config_data()
CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])

class LowerCaseFormatter(click.HelpFormatter):
    def write_usage(self, prog, args='', prefix='usage: '):
        super(LowerCaseFormatter, self).write_usage(prog, args, prefix)
click.Context.formatter_class = LowerCaseFormatter


@click.group(context_settings=CONTEXT_SETTINGS,
             options_metavar='[-h] [-V]',
             subcommand_metavar='<command> [<args>]',
             cls=config.OrderedGroup)
@click.version_option(__version__, '-V', '--version')
@click.pass_context
def cli(ctx):
    """
    Track completion of your jobs!
    """
    pass 


@click.command(short_help='Track <job>, either a shell command or an existing PID',
               no_args_is_help=True,
               options_metavar='[<options>]')
@click.argument('job', nargs=-1, metavar='<job>')
@click.option('-t', '--text', is_flag=True, 
              help='send SMS text at job exit')
@click.option('-e', '--email', is_flag=True, 
              help='send email at job exit')
@click.option('-d', '--database', is_flag=True, 
              help='store job details in database')
@click.option('-s', '--session', metavar='<session>',
              help='job session name for database')
@click.option('-u', '--unique', is_flag=True, 
              help='skip if session & job have completed previously with no errors')
@click.option('-o', '--output', is_flag=True,
              help='save stdout/stderr output when sending email notification')
@click.option('--shell', is_flag=True,
              help='use shell execution when tracking new job')
@click.option('-v', '--verbose', is_flag=True, 
              help='print job payloads and all info')
def track(job, text, email, database, session, unique, output, shell, verbose):
    """
    Track <job>, which is either a shell command or an existing PID
    """
    if len(job) == 1 and job[0].isdigit():
        pid = int(job[0])
        # Use PID tracking
        print(f"Tracking existing process PID at: {pid}")
        track_cli.track_existing(pid,
                                 to_db=database,
                                 session_name=session,
                                 send_text=text,
                                 send_email=email,
                                 verbose=verbose)
    else:
        # Run command and track execution
        joined_command = ' '.join(job)
        print(f"Tracking command `{joined_command}`")
        track_cli.track_new(joined_command,
                            use_shell=shell,
                            store_stdout=output,
                            save_filename=None,
                            to_db=database,
                            session_name=session,
                            unique=unique,
                            send_text=text,
                            send_email=email,
                            verbose=verbose)

cli.add_command(config.init)
cli.add_command(config.config_group)
cli.add_command(track)
cli.add_command(database.inspect)


if __name__ == '__main__':
    cli()