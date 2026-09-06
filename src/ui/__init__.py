"""
FaceTrace — Judge-Facing UI Subsystem (Step 5)
Provides forensic workstation server and static web assets.
"""

from .server import FaceTraceHTTPServer, run_server

__all__ = ["FaceTraceHTTPServer", "run_server"]
