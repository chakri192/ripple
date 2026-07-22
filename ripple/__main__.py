"""CLI entrypoint.

    python -m ripple triage <urn> [--no-write-back] [--columns] [--incident]
    python -m ripple root-cause <urn>
    python -m ripple watch [--interval 15] [--once]
"""
from __future__ import annotations

import argparse
import sys

from .triage import run_root_cause, run_triage
from .watch import watch


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="ripple",
        description="Data-incident triage agent for DataHub.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # triage (downstream impact)
    t = sub.add_parser("triage", help="Triage a broken asset (downstream impact).")
    t.add_argument("urn", help="URN of the broken dataset.")
    t.add_argument(
        "--no-write-back",
        action="store_true",
        help="Generate the report but do not modify the catalog.",
    )
    t.add_argument(
        "--columns",
        action="store_true",
        help="Also trace column-level lineage.",
    )
    t.add_argument(
        "--incident",
        action="store_true",
        help="Also raise a native DataHub Incident entity.",
    )

    # root-cause (upstream)
    rc = sub.add_parser(
        "root-cause", help="Trace upstream to rank likely sources of a symptom."
    )
    rc.add_argument("urn", help="URN of the asset showing bad data.")

    # watch (auto-trigger)
    w = sub.add_parser("watch", help="Poll for broken assets and auto-triage.")
    w.add_argument("--interval", type=int, default=15, help="Seconds between polls.")
    w.add_argument("--once", action="store_true", help="Run a single pass and exit.")

    # web (dashboard)
    wb = sub.add_parser("web", help="Launch the web dashboard.")
    wb.add_argument("--port", type=int, default=8000, help="Port to serve on.")

    args = parser.parse_args()

    if args.command == "triage":
        run_triage(
            args.urn,
            write_back=not args.no_write_back,
            with_columns=args.columns,
            raise_incident=args.incident,
        )
    elif args.command == "root-cause":
        run_root_cause(args.urn)
    elif args.command == "watch":
        watch(interval=args.interval, once=args.once)
    elif args.command == "web":
        from .web import serve

        print(f"◉  Ripple dashboard → http://localhost:{args.port}")
        serve(port=args.port)
    else:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
