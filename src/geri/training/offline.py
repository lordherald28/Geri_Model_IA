"""Deny Python socket/urllib access during training and synthetic benchmarks."""
from __future__ import annotations

from contextlib import ExitStack, contextmanager
from unittest.mock import patch


def _deny(*_args, **_kwargs):
    raise RuntimeError("network access is disabled by the offline training guard")


@contextmanager
def offline_execution():
    with ExitStack() as stack:
        stack.enter_context(patch("urllib.request.urlopen", _deny))
        stack.enter_context(patch("socket.create_connection", _deny))
        stack.enter_context(patch("socket.getaddrinfo", _deny))
        stack.enter_context(patch("socket.gethostbyname", _deny))
        stack.enter_context(patch("socket.socket.connect", _deny))
        stack.enter_context(patch("socket.socket.connect_ex", _deny))
        yield
