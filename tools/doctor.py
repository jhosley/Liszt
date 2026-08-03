#!/usr/bin/env python3
"""
Check this machine for everything Liszt needs, one line per check.

    python3 tools/doctor.py            # every check
    python3 tools/doctor.py --offline  # skip the package index probe

Each check prints one sentence: a pass, or a failure that says what it means
and what to do about it. The exit code is the number of failed checks, so 0
means the machine is healthy. Runs on the standard library only, so it works
before anything is installed.
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import socket
import ssl
import subprocess
import sys
import sysconfig
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
WHEELS = ROOT / "vendor" / "wheels"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from serve import default_port  # standard library only, safe before install


def venv_python() -> pathlib.Path | None:
    """Path to the virtual environment's Python, or None if there is none."""
    for rel in ("bin/python", "Scripts/python.exe"):
        p = ROOT / ".venv" / rel
        if p.exists():
            return p
    return None


def run_quiet(cmd: list[str]) -> subprocess.CompletedProcess | None:
    """Run a command, capture everything, and never raise."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception:
        return None


def human_size(n: float) -> str:
    if n >= 2**30:
        return f"{n / 2**30:.1f} GB"
    return f"{n / 2**20:.0f} MB"


class Doctor:
    def __init__(self) -> None:
        self.fails = 0

    def ok(self, sentence: str) -> None:
        print(f"pass: {sentence}")

    def note(self, sentence: str) -> None:
        """Something worth knowing that is not a fault. Does not affect the exit code."""
        print(f"note: {sentence}")

    def fail(self, sentence: str) -> None:
        print(f"fail: {sentence}")
        self.fails += 1


def check_python(d: Doctor) -> None:
    v = sys.version_info
    if v >= (3, 11):
        d.ok(f"Python {v.major}.{v.minor}.{v.micro} is new enough (3.11 is "
             f"the minimum; an offline install needs wheels built for this "
             f"exact version).")
    else:
        d.fail(f"Python {v.major}.{v.minor} is older than 3.11, which the "
               f"pinned packages require. On macOS install it with "
               f"'brew install python@3.11' or from python.org/downloads; on "
               f"Debian or Ubuntu use 'sudo apt install python3.11 "
               f"python3.11-venv'. Then run install.sh again.")


def check_venv_and_core(d: Doctor, vp: pathlib.Path | None) -> None:
    if vp is None:
        d.fail("there is no virtual environment at .venv, so the tools cannot "
               "run; run install.sh (or install.ps1 on Windows) first.")
        return
    r = run_quiet([str(vp), "-c", "import yaml, jsonschema, ruamel.yaml"])
    if r is not None and r.returncode == 0:
        d.ok("the virtual environment at .venv exists and the core packages "
             "import.")
    else:
        d.fail("the virtual environment at .venv exists but the core packages "
               "do not import; run install.sh again to reinstall them.")


def check_deck(d: Doctor, vp: pathlib.Path | None) -> None:
    if vp is None:
        return  # the core check above already said what to do
    probe = ("import importlib.util, sys\n"
             "if importlib.util.find_spec('pptx') is None: sys.exit(3)\n"
             "import pptx\n")
    r = run_quiet([str(vp), "-c", probe])
    if r is not None and r.returncode == 0:
        d.ok("the deck packages are installed, so the render command will "
             "work.")
    elif r is not None and r.returncode == 3:
        d.ok("the deck packages are not installed, which only matters for the "
             "render command; add them with: bash install.sh --with-deck "
             "(on Windows: install.ps1 -WithDeck).")
    else:
        d.fail("the deck packages are present but do not import; run "
               "install.sh --with-deck again to repair them.")


def check_externally_managed(d: Doctor, vp: pathlib.Path | None) -> None:
    marker = pathlib.Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED"
    if not marker.exists():
        d.ok("the system Python is not marked externally managed.")
    elif vp is not None:
        d.ok("the system Python is marked externally managed, but that does "
             "not matter here because everything installs into the .venv "
             "virtual environment.")
    else:
        d.fail("the system Python is marked externally managed, which blocks "
               "direct package installs; run install.sh, which creates the "
               ".venv virtual environment instead of touching the system "
               "Python.")


def check_index(d: Doctor) -> bool:
    """Probe the package index. Returns True when online installs can work."""
    try:
        ctx = ssl.create_default_context()
        with urllib.request.urlopen("https://pypi.org/simple/",
                                    timeout=10, context=ctx) as resp:
            resp.read(1)
        d.ok("the package index at pypi.org answers, so online installs can "
             "work.")
        return True
    except urllib.error.HTTPError as exc:
        d.fail(f"the package index at pypi.org refused the request (status "
               f"{exc.code}); a proxy may be blocking it, so if this keeps "
               f"failing point pip at an internal package mirror, or install "
               f"offline from a wheel folder you build elsewhere.")
        return False
    except Exception as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, ssl.SSLCertVerificationError) or \
                "CERTIFICATE_VERIFY_FAILED" in str(exc):
            d.fail("the package index gave a certificate error, which usually "
                   "means a company proxy inspects secure web traffic; set "
                   "SSL_CERT_FILE and PIP_CERT to the path of your company "
                   "root certificate bundle and try again.")
        else:
            d.fail("the package index at pypi.org did not answer, so online "
                   "installs will not work from here; point pip at an "
                   "internal package mirror, or install offline from a wheel "
                   "folder you build elsewhere.")
        return False


def check_disk(d: Doctor) -> None:
    need = 500 * 2**20
    free = shutil.disk_usage(ROOT).free
    if free >= need:
        d.ok(f"{human_size(free)} of free disk space is available, which is "
             f"enough.")
    else:
        d.fail(f"only {human_size(free)} of free disk space is left, and the "
               f"install needs about 500 MB; free some space first.")


def check_port(d: Doctor, port: int) -> None:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        d.ok(f"port {port} is free, so the serve command can use it.")
    except OSError:
        d.fail(f"port {port} is already in use; run ./liszt serve --port "
               f"with a different number.")
    finally:
        s.close()


def check_wheels(d: Doctor) -> None:
    """Report whether a local wheel folder exists. Its absence is normal, not a fault."""
    count = len(list(WHEELS.glob("*.whl"))) if WHEELS.is_dir() else 0
    if count:
        d.ok(f"{count} wheel files are in vendor/wheels, so an offline "
             f"install can work.")
    else:
        d.note("there is no vendor/wheels folder, which is normal; an offline "
               "install needs one, and you build it on a machine with package "
               "index access with: pip download -r requirements/base.txt -r "
               "requirements/deck.txt --only-binary=:all: --python-version "
               "3.11 --platform <target platform tag> -d vendor/wheels. An "
               "internal package mirror does the same job without a folder.")


def check_mac_quarantine(d: Doctor) -> None:
    targets = [ROOT, ROOT / "liszt", ROOT / "install.sh"]
    flagged = False
    for t in targets:
        if not t.exists():
            continue
        r = run_quiet(["xattr", "-p", "com.apple.quarantine", str(t)])
        if r is None:
            return  # no xattr command available, nothing to say
        if r.returncode == 0:
            flagged = True
            break
    if flagged:
        d.fail("macOS marked files in this folder as downloaded from the "
               "internet, which can block them from running; clear the mark "
               "by running this from the repo folder: "
               "xattr -dr com.apple.quarantine .")
    else:
        d.ok("no macOS download quarantine mark is on these files.")


def check_win_execution_policy(d: Doctor) -> None:
    r = run_quiet(["powershell", "-NoProfile", "-Command",
                   "Get-ExecutionPolicy"])
    if r is None or r.returncode != 0:
        return  # PowerShell did not answer, nothing useful to say
    policy = r.stdout.strip()
    if policy in ("Restricted", "AllSigned"):
        d.ok(f"the PowerShell execution policy is {policy}, which blocks "
             f"plain script runs, so start installs with: powershell "
             f"-ExecutionPolicy Bypass -File install.ps1.")
    else:
        d.ok(f"the PowerShell execution policy ({policy}) lets the install "
             f"script run.")


def check_win_long_paths(d: Doctor) -> None:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\FileSystem")
        value, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
        winreg.CloseKey(key)
    except OSError:
        value = 0
    except ImportError:
        return
    if value == 1:
        d.ok("Windows long path support is on.")
    else:
        d.ok("Windows long path support is off, which is fine unless a "
             "command fails with a path length error; if one does, keep this "
             "folder near the drive root or have an administrator turn the "
             "support on.")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true",
                    help="skip the package index probe and report on the "
                         "local wheel folder instead")
    ap.add_argument("--port", type=int, default=None,
                    help="check this port instead of the default serve port")
    args = ap.parse_args()

    d = Doctor()
    vp = venv_python()

    check_python(d)
    check_venv_and_core(d, vp)
    check_deck(d, vp)
    check_externally_managed(d, vp)

    index_ok = True
    if args.offline:
        index_ok = False  # skip the probe quietly; offline was asked for
    else:
        index_ok = check_index(d)

    check_disk(d)
    check_port(d, args.port if args.port is not None else default_port())

    # A local wheel folder only matters when an offline install would be needed.
    if not index_ok:
        check_wheels(d)

    if sys.platform == "darwin":
        check_mac_quarantine(d)
    if sys.platform == "win32":
        check_win_execution_policy(d)
        check_win_long_paths(d)

    print()
    if d.fails == 0:
        print("every check passed.")
    else:
        print(f"{d.fails} check(s) failed.")
    return d.fails


if __name__ == "__main__":
    sys.exit(main())
