import os
from pathlib import Path

# Create internal jort directory
JORT_DIR = f"{os.path.expanduser('~')}/.jort"
Path(f"{JORT_DIR}/").mkdir(mode=0o700, parents=True, exist_ok=True)
Path(f"{JORT_DIR}/config").touch(mode=0o600, exist_ok=True)