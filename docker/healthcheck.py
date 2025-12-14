import os
import sys
import urllib.request

# Inside a container, 0.0.0.0 is a bind-all address, not a destination.
host = os.getenv("APP_HOST", "127.0.0.1")
if host == "0.0.0.0":
    host = "127.0.0.1"

port = int(os.getenv("APP_PORT", "8080"))
url = f"http://{host}:{port}/api/health"

try:
    with urllib.request.urlopen(url, timeout=2) as resp:
        if resp.status != 200:
            sys.exit(1)
except Exception:
    sys.exit(1)

sys.exit(0)
