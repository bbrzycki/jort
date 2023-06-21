#!/usr/bin/env python3
import os
import errno
import json
import getpass
import argparse
import click

from . import _config
from . import track_cli
from ._version import __version__


CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])

class LowerCaseFormatter(click.HelpFormatter):
    def write_usage(self, prog, args='', prefix='usage: '):
        super(LowerCaseFormatter, self).write_usage(prog, args, prefix)
click.Context.formatter_class = LowerCaseFormatter

@click.group(context_settings=CONTEXT_SETTINGS,
             options_metavar='[-h] [-V]',
             subcommand_metavar='<command> [<args>]')
@click.version_option(__version__, '-V', '--version')
@click.pass_context
def cli(ctx):
    """
    Track completion of your jobs!
    """
    pass 


@cli.command(options_metavar='[-h]')
def config():
    """
    Configure user details and auth for notifications
    """
    config_data = _config.get_config_data()
    input_config_data = {
        "machine": input('What name should this device go by? ({}) '
                            .format(config_data.get("machine", ""))),
        "email": input('What email to use? ({}) '
                        .format(config_data.get("email", ""))),
        "smtp_server": input('What SMTP server does your email use? ({}) '
                                .format(config_data.get("smtp_server", ""))),
        "email_password": getpass.getpass('Email password? ({}) '
                                            .format(("*"*16 
                                                    if config_data.get("email_password") is not None 
                                                    else ""))),
        "twilio_receive_number": input('What phone number to receive SMS? ({}) '
                                        .format(config_data.get("twilio_receive_number", ""))),
        "twilio_send_number": input('What Twilio number to send SMS? ({}) '
                                    .format(config_data.get("twilio_send_number", ""))),
        "twilio_account_sid": input('Twilio Account SID? ({}) '
                                    .format(config_data.get("twilio_account_sid", ""))),
        "twilio_auth_token": getpass.getpass('Twilio Auth Token? ({}) '
                                                .format(("*"*16 
                                                        if config_data.get("twilio_auth_token") is not None 
                                                        else "")))
    }
    # Only save inputs if they aren't empty
    for key in input_config_data:
        if input_config_data[key] != "":
            config_data[key] = input_config_data[key]
    with open(f"{_config.JORT_DIR}/config", "w") as f:
        json.dump(config_data, f)


@cli.command(options_metavar='[<options>]')
def inspect():
    """
    Get saved job details from database
    """
    pass


@cli.command(short_help='Track <job>, either a shell command or an existing PID',
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



def main():
    parser = argparse.ArgumentParser(
        description='Track completion of your jobs!'
    )

    parser.add_argument(
        '-c',
        '--command',
        nargs='+',
        help='full command to track',
    )

    # May potentially support multiple processes
    parser.add_argument(
        '-p',
        '--pid',
        type=int,
        help='PID of existing job to track',
    )

    # Save stdout/stderr output
    parser.add_argument('-o',
                        '--output',
                        action='store_true',
                        help='save stdout/stderr output')

    parser.add_argument('--use-shell',
                        action='store_true',
                        help='use shell execution for tracking new process')

    # Send SMS at job completion
    parser.add_argument('-s',
                        '--sms',
                        action='store_true',
                        help='send SMS at job exit')
    
    # Send email at job completion
    parser.add_argument('-e',
                        '--email',
                        action='store_true',
                        help='send email at job exit')

    parser.add_argument('-d',
                        '--database',
                        action='store_true',
                        help='store job in database')
    
    parser.add_argument(
        '--session',
        type=str,
        help='job session name, for database',
    )

    parser.add_argument('-u',
                        '--unique',
                        action='store_true',
                        help='skip if session+job have completed previously with no errors')
    
    # Init / info
    parser.add_argument('-i',
                        '--init',
                        action='store_true',
                        help='enter information needed for notifications')

    # Verbose
    parser.add_argument('-v',
                        '--verbose',
                        action='store_true',
                        help='print payloads and all info')

    # Version
    parser.add_argument('-V',
                        '--version',
                        action='version',
                        version=f'%(prog)s {__version__}'
                        )

    args = parser.parse_args()

    if args.init:
        config_data = _config.get_config_data()
        input_config_data = {
            "machine": input('What name should this device go by? ({}) '
                                .format(config_data.get("machine", ""))),
            "email": input('What email to use? ({}) '
                            .format(config_data.get("email", ""))),
            "smtp_server": input('What SMTP server does your email use? ({}) '
                                    .format(config_data.get("smtp_server", ""))),
            "email_password": getpass.getpass('Email password? ({}) '
                                                .format(("*"*16 
                                                        if config_data.get("email_password") is not None 
                                                        else ""))),
            "twilio_receive_number": input('What phone number to receive SMS? ({}) '
                                            .format(config_data.get("twilio_receive_number", ""))),
            "twilio_send_number": input('What Twilio number to send SMS? ({}) '
                                        .format(config_data.get("twilio_send_number", ""))),
            "twilio_account_sid": input('Twilio Account SID? ({}) '
                                        .format(config_data.get("twilio_account_sid", ""))),
            "twilio_auth_token": getpass.getpass('Twilio Auth Token? ({}) '
                                                    .format(("*"*16 
                                                            if config_data.get("twilio_auth_token") is not None 
                                                            else "")))
        }
        # Only save inputs if they aren't empty
        for key in input_config_data:
            if input_config_data[key] != "":
                config_data[key] = input_config_data[key]
        with open(f"{_config.JORT_DIR}/config", "w") as f:
            json.dump(config_data, f)            
    if args.command and args.pid:
        parser.error('Please specify only one command or process to track.')
    elif args.command is None and args.pid is None and not args.init:
        parser.print_help()
    elif args.command:
        # # Grab all aws credentials; either from file or interactively
        # aws_credentials = auth.login()
        joined_command = ' '.join(args.command)
        print(f"Tracking command '{joined_command}'")
        track_cli.track_new(joined_command,
                            use_shell=args.use_shell,
                            store_stdout=args.output,
                            save_filename=None,
                            to_db=args.database,
                            session_name=args.session,
                            unique=args.unique,
                            send_text=args.sms,
                            send_email=args.email,
                            verbose=args.verbose)
    elif args.pid:
        # # Grab all aws credentials; either from file or interactively
        # aws_credentials = auth.login()
        print(f"Tracking existing process PID at: {args.pid}")
        track_cli.track_existing(args.pid,
                                 to_db=args.database,
                                 session_name=args.session,
                                 send_text=args.sms,
                                 send_email=args.email,
                                 verbose=args.verbose)
    elif args.init:
        pass
    else:
        parser.error('Something went wrong!')

if __name__ == '__main__':
    cli()