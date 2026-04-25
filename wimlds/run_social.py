#!/usr/bin/env python3
"""Compatibility wrapper for the unified social CLI command."""

import sys

from wimlds.cli import cli


if __name__ == "__main__":
    sys.argv.insert(1, "social")
    cli()
