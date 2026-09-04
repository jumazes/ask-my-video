"""Desktop entry point: runs the same FastAPI backend locally and shows it
in a native OS window (via pywebview) instead of a browser tab.

Why this exists: the deployed web version (see README - Deploy section)
can get blocked by YouTube's anti-bot checks when requests come from a
cloud host's datacenter IP address. Running the exact same backend on
your own machine sidesteps that entirely - requests then come from your
own home internet connection, like a normal browser's would.
"""

import threading
import time

import requests
import webview

import uvicorn
from backend.main import app

HOST = "127.0.0.1"
PORT = 8000


def _run_server() -> None:
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def _wait_until_ready(timeout: float = 15) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            requests.get(f"http://{HOST}:{PORT}/api/health", timeout=1)
            return
        except requests.exceptions.ConnectionError:
            time.sleep(0.2)
    raise RuntimeError("Backend server did not start in time")


def main() -> None:
    threading.Thread(target=_run_server, daemon=True).start()
    _wait_until_ready()

    webview.create_window(
        "Video Q&A", f"http://{HOST}:{PORT}", width=960, height=760, min_size=(640, 480)
    )
    webview.start()


if __name__ == "__main__":
    main()
