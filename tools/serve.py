#!/usr/bin/env python3
"""
Rebuild the viewer, then serve it on a local address.

    python3 tools/serve.py                    # rebuild, serve, open a browser
    python3 tools/serve.py --port 8765        # pick the port yourself
    python3 tools/serve.py --published-only   # hide draft records
    python3 tools/serve.py --org platform-eng # apply a coverage overlay

Why the local server exists: when the viewer page is opened straight from a
file, the browser gives it one storage bucket that is shared by every other
page opened from a file on the same machine, so a second copy of the viewer can
silently overwrite an in-progress session, and one major browser refuses
storage for file pages entirely, which means a page refresh loses the session.
Serving the page from a real local address gives each person's session its own
isolated storage, keeps every browser working, and makes a refresh survivable.

The default port is 8700 plus a number derived from your user account, so two
people on a shared server get different ports without thinking about it. Pass
--port to override. The server listens on 127.0.0.1 only, so nobody else on
the network can reach it.
"""
from __future__ import annotations

import argparse
import functools
import getpass
import http.server
import os
import pathlib
import sys
import webbrowser
import zlib

# Only standard library imports above this line. tools/doctor.py imports
# default_port() from this file, and it must work before any packages install.

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "build" / "viewer"


def default_port() -> int:
    """8700 plus a per-user offset in 0..249, stable across runs.

    The offset is the numeric user id where the system has one, or a hash of
    the username on Windows. Two people on a shared server therefore land on
    different ports by default.
    """
    if hasattr(os, "getuid"):
        seed = os.getuid()
    else:
        try:
            name = getpass.getuser()
        except Exception:
            name = "unknown"
        seed = zlib.crc32(name.encode("utf-8", "replace"))
    return 8700 + seed % 250


def rebuild(include_drafts: bool, org: str | None) -> None:
    """Run the build_viewer.py logic so the served page is always current."""
    tools_dir = str(pathlib.Path(__file__).resolve().parent)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)
    import build_viewer

    argv = ["build_viewer.py", "--out", str(OUT)]
    if include_drafts:
        argv.append("--include-drafts")
    if org:
        argv += ["--org", org]
    saved = sys.argv
    sys.argv = argv
    try:
        build_viewer.main()
    finally:
        sys.argv = saved


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Serve files without logging every request to the terminal."""

    def log_message(self, format, *args):  # noqa: A002 (stdlib signature)
        pass


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=None,
                    help="port to listen on; the default is 8700 plus a number "
                         "derived from your user account")
    # Drafts are INCLUDED by default here, which is the opposite of
    # build_viewer.py. That tool builds an artifact you might hand out, so it
    # shows published records only. This one is the tool you run during a
    # working session, where the records you are working on are exactly the
    # drafts. A session that opened on an almost empty library because
    # everything in it was still a draft is a confusing first five minutes.
    ap.add_argument("--published-only", action="store_true",
                    help="hide draft records; by default a served session "
                         "shows everything, drafts included")
    ap.add_argument("--org",
                    help="apply a coverage overlay while rebuilding, "
                         "same as build_viewer.py")
    ap.add_argument("--no-browser", action="store_true",
                    help="do not try to open a browser")
    args = ap.parse_args()

    port = args.port if args.port is not None else default_port()

    print("Rebuilding the viewer...")
    rebuild(not args.published_only, args.org)

    handler = functools.partial(QuietHandler, directory=str(OUT))
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError as exc:
        print(f"Could not listen on port {port} ({exc.strerror or exc}); "
              f"another program may be using it, so run again with --port and "
              f"a different number.", file=sys.stderr)
        return 1

    address = f"http://127.0.0.1:{port}/liszt-viewer.html"
    print(f"\nServing the viewer at {address}")
    print("The page is reachable from this machine only. Press Ctrl+C to stop "
          "the server.")

    if not args.no_browser:
        try:
            opened = webbrowser.open(address)
        except Exception:
            opened = False
        if not opened:
            print("No browser opened here; paste the address above into one "
                  "yourself.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
