"""Minimal CLI entrypoint for BrewPress."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="brewpress",
        description="BrewPress project bootstrap CLI.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print the current BrewPress version.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.version:
        from brewpress import __version__

        print(__version__)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
