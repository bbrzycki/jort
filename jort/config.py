import os
import json
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