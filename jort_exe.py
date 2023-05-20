#!/usr/bin/env python3
import os
import errno
import argparse

from jort import config
from jort import track_cli


if __name__ == '__main__':
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

    # Verbose
    parser.add_argument('-v',
                        '--verbose',
                        action='store_true',
                        help='print payloads and all info')

    args = parser.parse_args()

    if args.command and args.pid:
        parser.error('Please specify only one command or process to track.')
    elif args.command is None and args.pid is None:
        parser.print_help()
    elif args.command:
        # # Grab all aws credentials; either from file or interactively
        # aws_credentials = auth.login()
        joined_command = ' '.join(args.command)
        print(f"Tracking command '{joined_command}'")
        track_cli.track_new(joined_command,
                            store_stdout=False,
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
    else:
        parser.error('Something went wrong!')
