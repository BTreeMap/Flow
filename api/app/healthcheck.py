"""Container healthcheck entry point — role-agnostic, no configuration required.

The API and worker share one image, so the baked ``HEALTHCHECK`` must work for
either role *without* a flag that older deployments would lack. It simply checks
both liveness signals and is healthy if **either** holds:

* HTTP ``GET /healthz`` on ``$API_PORT`` returns a 2xx (the API is serving).
  ``localhost`` resolves on both IPv4 and IPv6, so this works whether uvicorn
  bound v4, v6, or dual-stack (``::``).
* A fresh worker heartbeat file exists (the worker loop is iterating).

The two signals are mutually exclusive per container because the heartbeat lives
in a **container-local** temp path, not on the shared ``flow-data`` volume: an
API container therefore never sees the worker's heartbeat, so a dead API server
cannot masquerade as healthy off the worker's signal, and vice-versa. The probe
is dependency-light (stdlib + :mod:`app.config`) and cheap enough to run both
checks every interval.

Exit code ``0`` means healthy; any non-zero means unhealthy.
"""

from __future__ import annotations

import os
import sys
import time
import urllib.request

from app import config

# Heartbeat file the worker loop refreshes once per iteration (~5s poll). It must
# be a FIXED, absolute path because the worker (the writer) and this healthcheck
# (a separately-launched `python -m app.healthcheck` process) are different
# processes that must agree on the exact location. A literal avoids any reliance
# on tempfile.gettempdir()/$TMPDIR, which could resolve differently between the
# two processes. It lives in the container-local /tmp (world-writable, sticky),
# NOT under the shared data volume, so only this container observes it.
HEARTBEAT_PATH = "/tmp/flow-worker.heartbeat"

# A heartbeat older than this is treated as a wedged loop. Generous relative to
# the ~5s poll so a single slow iteration never flaps the container unhealthy.
HEARTBEAT_MAX_AGE_S = 60.0


def _heartbeat_fresh() -> bool:
    """Return ``True`` when the worker heartbeat exists and is recent."""
    try:
        age = time.time() - os.path.getmtime(HEARTBEAT_PATH)
    except OSError:
        return False
    return age < HEARTBEAT_MAX_AGE_S


def _healthz_ok() -> bool:
    """Return ``True`` when ``GET /healthz`` returns a 2xx."""
    url = f"http://localhost:{config.get_port()}/healthz"
    try:
        with urllib.request.urlopen(url, timeout=4) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def main() -> int:
    """Healthy if either liveness signal holds; checks the cheap one first."""
    # Heartbeat is a single stat() — check it first so a worker container never
    # pays for an HTTP round-trip to a port nothing is listening on.
    if _heartbeat_fresh():
        return 0
    if _healthz_ok():
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
