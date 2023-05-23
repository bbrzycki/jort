#!/usr/bin/env python3
import os
import errno
import json
import getpass
import argparse

from . import config
from . import track_cli


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
        nargs=1,
        type=int,
        help='PID of existing job to track',
    )

    # Save stdout/stderr output
    parser.add_argument('-o',
                        '--output',
                        action='store_true',
                        help='save stdout/stderr output')

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
    
    # Init / info
    parser.add_argument('-i',
                        '--init',
                        action='store_true',
                        help='enter information needed for notifcations')

    # Verbose
    parser.add_argument('-v',
                        '--verbose',
                        action='store_true',
                        help='print payloads and all info')

    args = parser.parse_args()

    if args.init:
        config_data = config.get_config_data()
        input_config_data = {
            "machine": input('What name should this device go by? ({}) '
                             .format(config_data.get("machine", ""))),
            "email": input('What email to use? ({}) '
                           .format(config_data.get("email", ""))),
            "smtp_server": input('What SMTP server does your email use? ({}) '
                                 .format(config_data.get("smtp_server", ""))),
            "email_password": getpass.getpass('Email password? ({}) '
                                              .format(("*"*16 
                                                       if config_data.get("email_password", "") is not None 
                                                       else ""))),
            "twilio_receive_number": input('What phone number to receive SMS? ({}) '
                                           .format(config_data.get("twilio_receive_number", ""))),
            "twilio_send_number": input('What Twilio number to send SMS? ({}) '
                                        .format(config_data.get("twilio_send_number", ""))),
            "twilio_account_sid": input('Twilio Account SID? ({}) '
                                        .format(config_data.get("twilio_account_sid", ""))),
            "twilio_auth_token": getpass.getpass('Twilio Auth Token? ({}) '
                                                 .format(("*"*16 
                                                         if config_data.get("twilio_auth_token", "") is not None 
                                                         else "")))
        }
        # Only save inputs if they aren't empty
        for key in input_config_data:
            if input_config_data[key] != "":
                config_data[key] = input_config_data[key]
        with open(f"{config.JORT_DIR}/config", "w") as f:
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
                            store_stdout=args.output,
                            save_filename=None,
                            send_sms=args.sms,
                            send_email=args.email,
                            verbose=args.verbose)
    elif args.pid:
        # # Grab all aws credentials; either from file or interactively
        # aws_credentials = auth.login()
        print(f"Tracking existing process PID at: {args.pid[0]}")
        track_cli.track_existing(args.pid[0],
                                 send_sms=args.sms,
                                 send_email=args.email,
                                 verbose=args.verbose)
    elif args.init:
        pass
    else:
        parser.error('Something went wrong!')

if __name__ == '__main__':
    main()