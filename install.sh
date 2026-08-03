#!/usr/bin/env bash
# Install Liszt's Python packages into a virtual environment inside this repo.
#
#   bash install.sh                 # core packages, needs package index access
#   bash install.sh --with-deck     # also install the slide deck packages
#   bash install.sh --offline       # install from a local vendor/wheels folder,
#                                   # which you build first (see the message the
#                                   # script prints when it is missing)
#
# No sudo. Nothing outside this repo is changed: the script writes the .venv
# folder and build output here, and that is all.

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

WITH_DECK=0
OFFLINE=0
for arg in "$@"; do
  case "$arg" in
    --with-deck) WITH_DECK=1 ;;
    --offline)   OFFLINE=1 ;;
    -h|--help)
      sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *)
      echo "unknown option: $arg (known options: --with-deck, --offline)" >&2
      exit 2 ;;
  esac
done

# ---- find a Python that is at least 3.11 -----------------------------------
#
# 3.11 is the floor, not 3.10, because the pinned packages in requirements/
# require it. Ask for a specific version before the generic python3 name: a
# machine often has an older python3 on the path and a newer one installed
# alongside it, and taking the generic name first would miss the newer one.

PY=""
for candidate in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
    PY="$candidate"
    break
  fi
done
if [ -z "$PY" ]; then
  found="$(python3 -c 'import sys; print(".".join(str(n) for n in sys.version_info[:3]))' 2>/dev/null || echo "none")"
  echo "" >&2
  echo "Liszt needs Python 3.11 or newer. The Python on this machine is $found." >&2
  echo "" >&2
  echo "To install a newer Python:" >&2
  echo "" >&2
  echo "  macOS, with Homebrew:   brew install python@3.11" >&2
  echo "  macOS, without it:      download the installer from python.org/downloads" >&2
  echo "  Debian or Ubuntu:       sudo apt install python3.11 python3.11-venv" >&2
  echo "  Red Hat or Fedora:      sudo dnf install python3.11" >&2
  echo "" >&2
  echo "Then run this script again. It will find the new version on its own." >&2
  exit 1
fi
echo "Using $("$PY" -c 'import sys; print("Python " + ".".join(str(n) for n in sys.version_info[:3]))') at $(command -v "$PY")."

# ---- offline mode groundwork -----------------------------------------------

if [ "$OFFLINE" = 1 ]; then
  if ! ls "$ROOT"/vendor/wheels/*.whl >/dev/null 2>&1; then
    echo "" >&2
    echo "The offline install needs a local folder of wheel files at vendor/wheels, and there is none here." >&2
    echo "This repository does not ship wheel files. Build the folder once on a machine that has package" >&2
    echo "index access, matching the Python version and the platform of THIS machine:" >&2
    echo "" >&2
    echo "  pip download -r requirements/base.txt -r requirements/deck.txt \\" >&2
    echo "      --only-binary=:all: \\" >&2
    echo "      --python-version 3.11 --platform manylinux_2_28_x86_64 \\" >&2
    echo "      -d vendor/wheels" >&2
    echo "" >&2
    echo "Platform tags: manylinux_2_28_x86_64 for Linux x86_64, macosx_11_0_arm64 for Apple Silicon," >&2
    echo "win_amd64 for Windows. Then copy vendor/wheels here and run this script again." >&2
    echo "" >&2
    echo "If your organization runs an internal package mirror (Artifactory, Nexus, devpi), point pip at" >&2
    echo "it instead and run this script with no flags:" >&2
    echo "" >&2
    echo "  pip config set global.index-url <your internal index url>" >&2
    echo "  bash install.sh" >&2
    echo "" >&2
    echo "The full procedure is in docs/09-air-gapped.md, section 6." >&2
    exit 1
  fi
  echo "Offline mode: installing from the wheel files in vendor/wheels, with no package index."
  echo "The wheels have to match this Python version and platform, or pip will not find them."
fi

# ---- create the virtual environment ----------------------------------------

VENV_PY="$ROOT/.venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  if ! "$PY" -m venv --help >/dev/null 2>&1; then
    echo "This Python is missing the venv module, so it cannot create a virtual environment." >&2
    echo "On Debian or Ubuntu, install the python3-venv package (match your version, for example python3.11-venv), then run this script again." >&2
    exit 1
  fi
  echo "Creating the virtual environment at .venv ..."
  venv_out="$("$PY" -m venv "$ROOT/.venv" 2>&1)" || {
    echo "$venv_out" >&2
    case "$venv_out" in
      *ensurepip*)
        echo "Your Python cannot finish creating a virtual environment because its ensurepip piece is missing." >&2
        echo "On Debian or Ubuntu, install the python3-venv package (match your version, for example python3.11-venv), then run this script again." >&2
        ;;
    esac
    exit 1
  }
fi
if [ ! -x "$VENV_PY" ]; then
  echo "The virtual environment at .venv looks broken (no Python inside it); delete the .venv folder and run this script again." >&2
  exit 1
fi

# ---- install packages -------------------------------------------------------

# Runs pip, stays quiet on success, and explains the two failures people
# actually hit: certificate interception and an externally managed Python.
run_pip() {
  pip_out="$("$VENV_PY" -m pip install --quiet --no-cache-dir "$@" 2>&1)" && return 0
  echo "$pip_out" >&2
  case "$pip_out" in
    *CERTIFICATE_VERIFY_FAILED*|*"certificate verify failed"*|*SSLError*|*SSLCertVerificationError*)
      echo "That is a certificate failure, which usually means a company proxy inspects secure web traffic; set SSL_CERT_FILE and PIP_CERT to the path of your company root certificate bundle and run this script again." >&2
      ;;
  esac
  case "$pip_out" in
    *externally-managed-environment*)
      echo "This Python is marked externally managed, which blocks installs outside a virtual environment; delete the .venv folder and run this script again so a fresh one is created." >&2
      ;;
  esac
  return 1
}

install_tier() {
  if [ "$OFFLINE" = 1 ]; then
    run_pip --no-index --find-links "$ROOT/vendor/wheels" "$@"
  else
    run_pip "$@"
  fi
}

if [ "$OFFLINE" = 0 ]; then
  "$VENV_PY" -m pip install --quiet --no-cache-dir --upgrade pip >/dev/null 2>&1 ||
    echo "Note: could not upgrade pip; continuing with the version already in the virtual environment."
fi

echo "Installing the core packages ..."
install_tier -r "$ROOT/requirements/base.txt" || exit 1
echo "Installed the core packages."

if [ "$WITH_DECK" = 1 ]; then
  echo "Installing the deck packages ..."
  install_tier -r "$ROOT/requirements/deck.txt" || exit 1
  echo "Installed the deck packages."
fi

# ---- self test --------------------------------------------------------------

echo ""
echo "Self test:"
SELF_TEST_FAILED=0

# The coverage and viewer tools include drafts here so the self test still
# proves the install works in a library where nothing is published yet.
self_test() {
  st_name="$1"
  shift
  if st_out="$("$VENV_PY" "$@" 2>&1)"; then
    echo "  $st_name: ok"
  else
    echo "  $st_name: FAILED"
    echo "$st_out" | sed 's/^/    /'
    SELF_TEST_FAILED=1
  fi
}

self_test "tools/validate.py" "$ROOT/tools/validate.py"
self_test "tools/coverage.py" "$ROOT/tools/coverage.py" --include-drafts
self_test "tools/build_viewer.py" "$ROOT/tools/build_viewer.py" --include-drafts

if [ "$SELF_TEST_FAILED" = 1 ]; then
  echo ""
  echo "The install finished, but the self test failed; the output above says which tool broke and why." >&2
  exit 1
fi

# ---- done -------------------------------------------------------------------

echo ""
echo "Done. Next, run:"
echo "  ./liszt doctor"
echo "  ./liszt serve"
