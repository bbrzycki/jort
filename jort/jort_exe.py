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


class OrderedGroup(click.Group):
    def __init__(self, name=None, commands=None, **attrs):
        super(OrderedGroup, self).__init__(name, commands, **attrs)
        self.commands = commands or {}

    def list_commands(self, ctx):
        return self.commands
    

@click.group(context_settings=CONTEXT_SETTINGS,
             options_metavar='[-h] [-V]',
             subcommand_metavar='<command> [<args>]',
             cls=OrderedGroup)
@click.version_option(__version__, '-V', '--version')
@click.pass_context
def cli(ctx):
    """
    Track completion of your jobs!
    """
    pass 


@click.group(name='config',
             chain=True, 
             options_metavar='[-h]', 
             subcommand_metavar='<command> [<args>] [<command2> [<args>]]...',
             cls=OrderedGroup)
def config_group():
    """
    Configure user details and auth for notifications
    """
    pass


@click.command(name='general', options_metavar='[<options>]')
@click.option("--machine", prompt="Machine name", 
              default=lambda: config_data.get("machine", socket.gethostname()),
              show_default=config_data.get("machine", socket.gethostname()))
@click.option("--data-dir", prompt="Location for storing jort data (parent directory)", 
              default=lambda: config_data.get("data_dir", os.path.expanduser("~")),
              show_default=config_data.get("data_dir", os.path.expanduser("~")))
def config_general(machine, data_dir):
    """
    Configure general details
    """
    if machine != "":
        config_data["machine"] = machine
    if data_dir != "":
        config_data["data_dir"] = data_dir
        jort_data_dir = os.path.join(data_dir, ".jort")
        Path(jort_data_dir).mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(config.CONFIG_PATH, "w") as f:
        json.dump(config_data, f)


@click.command(name='email', options_metavar='[<options>]')
@click.option("--email", prompt=True, 
              default=lambda: config_data.get("email", ""),
              show_default=config_data.get("email"))
@click.option("--email-password", prompt=True, hide_input=True,
              default=lambda: "*"*8 if config_data.get("email_password") is not None else "",
              show_default="*"*8 if config_data.get("email_password") is not None else None)
@click.option("--smtp-server", prompt="SMTP server", 
              default=lambda: config_data.get("smtp_server", ""),
              show_default=config_data.get("smtp_server"))
def config_email(email, email_password, smtp_server):
    """
    Configure e-mail authentication
    """
    if email != "":
        config_data["email"] = email
    if email_password not in ["", "*"*8]:
        config_data["email_password"] = email_password
    if smtp_server != "":
        config_data["smtp_server"] = smtp_server
    with open(config.CONFIG_PATH, "w") as f:
        json.dump(config_data, f)


@click.command(name='text', options_metavar='[<options>]')
@click.option("--twilio-receive-number", prompt=True, 
              default=lambda: config_data.get("twilio_receive_number", ""),
              show_default=config_data.get("twilio_receive_number"))
@click.option("--twilio-send-number", prompt=True, 
              default=lambda: config_data.get("twilio_send_number", ""),
              show_default=config_data.get("twilio_send_number"))
@click.option("--twilio-account-sid", prompt=True, 
              default=lambda: config_data.get("twilio_account_sid", ""),
              show_default=config_data.get("twilio_account_sid"))
@click.option("--twilio-auth-token", prompt=True, hide_input=True,
              default=lambda: "*"*8 if config_data.get("twilio_auth_token") is not None else "",
              show_default="*"*8 if config_data.get("twilio_auth_token") is not None else None)
def config_text(twilio_receive_number, twilio_send_number, twilio_account_sid, twilio_auth_token):
    """
    Configure SMS text authentication
    """
    if twilio_receive_number != "":
        config_data["twilio_receive_number"] = twilio_receive_number
    if twilio_send_number != "":
        config_data["twilio_send_number"] = twilio_send_number
    if twilio_account_sid != "":
        config_data["twilio_account_sid"] = twilio_account_sid
    if twilio_auth_token not in ["", "*"*8]:
        config_data["twilio_auth_token"] = twilio_auth_token
    with open(config.CONFIG_PATH, "w") as f:
        json.dump(config_data, f)


@click.command(name='all', options_metavar='[<options>]')
@click.option("--machine", prompt="Machine name", 
              default=lambda: config_data.get("machine", socket.gethostname()),
              show_default=config_data.get("machine", socket.gethostname()))
@click.option("--data-dir", prompt="Location for storing jort data", 
              default=lambda: config_data.get("data_dir", os.path.expanduser("~")),
              show_default=config_data.get("data_dir", os.path.expanduser("~")))
@click.option("--twilio-receive-number", prompt=True, 
              default=lambda: config_data.get("twilio_receive_number", ""),
              show_default=config_data.get("twilio_receive_number"))
@click.option("--twilio-send-number", prompt=True, 
              default=lambda: config_data.get("twilio_send_number", ""),
              show_default=config_data.get("twilio_send_number"))
@click.option("--twilio-account-sid", prompt=True, 
              default=lambda: config_data.get("twilio_account_sid", ""),
              show_default=config_data.get("twilio_account_sid"))
@click.option("--twilio-auth-token", prompt=True, hide_input=True,
              default=lambda: "*"*8 if config_data.get("twilio_auth_token") is not None else "",
              show_default="*"*8 if config_data.get("twilio_auth_token") is not None else None)
@click.option("--email", prompt=True, 
              default=lambda: config_data.get("email", ""),
              show_default=config_data.get("email"))
@click.option("--email-password", prompt=True, hide_input=True,
              default=lambda: "*"*8 if config_data.get("email_password") is not None else "",
              show_default="*"*8 if config_data.get("email_password") is not None else None)
@click.option("--smtp-server", prompt="SMTP server", 
              default=lambda: config_data.get("smtp_server", ""),
              show_default=config_data.get("smtp_server"))
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
    print(database.print_jobs(session=session, tail=rows, full_details=full_details))


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
cli.add_command(config_group)
cli.add_command(track)
cli.add_command(inspect)

config_group.add_command(config_general)
config_group.add_command(config_email)
config_group.add_command(config_text)
config_group.add_command(config_all)


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
        config_data = config._get_config_data()
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
        with open(config.CONFIG_PATH, "w") as f:
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