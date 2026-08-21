"""Internal detached worker entry point."""

import argparse
import json
import os

from . import track_cli


def main():
    parser = argparse.ArgumentParser(description="Jort detached worker")
    parser.add_argument("--spec", required=True)
    args = parser.parse_args()
    with open(args.spec, "r") as stream:
        spec = json.load(stream)
    try:
        os.unlink(args.spec)
    except FileNotFoundError:
        pass

    if spec.get("mode") == "existing":
        track_cli.track_existing(
            spec["pid"],
            to_db=True,
            session_name=spec.get("session_name"),
            send_text=spec.get("send_text", False),
            send_email=spec.get("send_email", False),
            job_id=spec.get("job_id"),
            timeout_seconds=spec.get("timeout_seconds"),
        )
    else:
        track_cli.track_new(
            spec["command"],
            use_shell=spec.get("use_shell", False),
            store_stdout=spec.get("store_stdout", False),
            to_db=True,
            session_name=spec.get("session_name"),
            send_text=spec.get("send_text", False),
            send_email=spec.get("send_email", False),
            cwd=spec.get("cwd"),
            max_output_bytes=spec.get("max_output_bytes"),
            quiet=True,
            job_id=spec.get("job_id"),
            timeout_seconds=spec.get("timeout_seconds"),
        )


if __name__ == "__main__":
    main()
