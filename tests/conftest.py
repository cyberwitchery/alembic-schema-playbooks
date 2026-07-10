import sys
from pathlib import Path

# make ``import validate`` (the repo-root module) work from the test suite
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
