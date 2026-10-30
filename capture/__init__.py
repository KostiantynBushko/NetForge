"""Traffic capture.

A capture session runs the system capture tool and writes a libpcap file.
The BPF filter builder is a pure function over a small model, so a filter
can be constructed and checked without a capture running.
"""

from __future__ import annotations

from netforge.capture.session import (
    BpfFilter,
    CaptureFilterRequest,
    CaptureOperation,
    CaptureResponse,
    CaptureSession,
)

__all__ = [
    "BpfFilter",
    "CaptureFilterRequest",
    "CaptureOperation",
    "CaptureResponse",
    "CaptureSession",
]
