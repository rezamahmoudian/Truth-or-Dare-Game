"""Check API and all background processes without exposing diagnostic bodies."""
import os
import subprocess
import sys
from urllib.request import Request, urlopen

try:
    host = os.environ["ALLOWED_HOSTS"].split(",")[0].strip()
    with urlopen(Request("http://127.0.0.1:3000/api/health/", headers={"Host": host}), timeout=8) as response:
        if response.status != 200:
            sys.exit(1)
    result = subprocess.run(["supervisorctl", "-c", "/app/deploy/liara/supervisord.conf", "status"],
                            capture_output=True, text=True, timeout=8)
    lines = result.stdout.strip().splitlines()
    sys.exit(0 if result.returncode == 0 and len(lines) == 4 and all("RUNNING" in line for line in lines) else 1)
except Exception:
    sys.exit(1)
