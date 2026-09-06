#!/usr/bin/env python3
"""
FaceTrace — Launch Judge-Facing Forensic Workstation
Presentation Layer Server

Usage:
  python scripts/serve_ui.py
  python scripts/serve_ui.py --port 8080 --no-browser
"""

import argparse
from pathlib import Path
import sys

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from src.ui.server import run_server


def main():
    parser = argparse.ArgumentParser(
        description="Launch FaceTrace Forensic Workstation Web UI for Hackathon Judging"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000)"
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open browser on startup"
    )

    args = parser.parse_args()
    run_server(host=args.host, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
