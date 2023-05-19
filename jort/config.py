import os
from pathlib import Path

# Create internal jort directory
JORT_DIR = f"{os.path.expanduser('~')}/.jort"
Path(f"{JORT_DIR}/").mkdir(parents=True, exist_ok=True)
Path(f"{JORT_DIR}/config").touch(exist_ok=True)