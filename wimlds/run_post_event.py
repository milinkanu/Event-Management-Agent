#!/usr/bin/env python3
"""Compatibility wrapper for the unified post-event agent CLI command."""

import sys

from wimlds.cli import cli


if __name__ == "__main__":
    sys.argv.insert(1, "post-event-agent")
    cli()
