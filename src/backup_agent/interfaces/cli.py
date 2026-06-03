"""Command line interface helpers."""

from __future__ import annotations

from argparse import ArgumentParser


def build_parser() -> ArgumentParser:
    """Build the command line parser."""

    parser = ArgumentParser(prog="backup-agent", description="Backup agent entrypoint")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--run-once",
        action="store_true",
        help="Execute a single backup cycle and exit (default).",
    )
    mode.add_argument(
        "--schedule",
        action="store_true",
        help="Run the internal daily scheduler loop.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="backup-agent 0.1.0",
    )
    return parser
