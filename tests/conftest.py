"""Pytest compatibility hooks for the benchmark suite.

The old integration tests accepted ``--agent-url`` so CI still passes it. The
current default suite uses mocked transports and does not contact an external
agent, but keeping the option registered avoids breaking existing workflows.
"""

from __future__ import annotations


def pytest_addoption(parser):
    parser.addoption(
        "--agent-url",
        default=None,
        help="Legacy external agent URL option. Accepted for CI compatibility.",
    )
    parser.addoption(
        "--agent-port",
        default=None,
        help="Legacy local agent port option. Accepted for CI compatibility.",
    )
