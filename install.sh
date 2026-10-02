#!/bin/sh
# Install into a virtual environment. No shell activation is required.
set -eu

case "${1-}" in
    -h|--help)
        cat <<'EOF'
Usage: sh install.sh

Install Fast Verify Lab for macOS, Linux, or WSL.
Python 3.11 or later and network access to build dependencies are required.
The installer creates or reuses .venv beside this script.

Optional environment variables:
  FAST_VERIFY_PYTHON  Python executable name or full path.
  FAST_VERIFY_VENV    Virtual environment path. Relative paths use the repository root.

Run the app with: sh run.sh
Run an offline demo with: sh run.sh demo
EOF
        exit 0
        ;;
    '') ;;
    *) printf '%s\n' 'Unknown option. Use: sh install.sh --help' >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then
    printf '%s\n' 'Use: sh install.sh' >&2
    exit 2
fi

project_dir=$(CDPATH= cd -P "$(dirname "$0")" && pwd)
venv_dir=${FAST_VERIFY_VENV:-"$project_dir/.venv"}
case "$venv_dir" in
    /*) ;;
    *) venv_dir="$project_dir/$venv_dir" ;;
esac
venv_python="$venv_dir/bin/python"
version_check='import os, sys; sys.exit(0 if os.name == "posix" and sys.version_info >= (3, 11) else 1)'

if [ -e "$venv_dir" ]; then
    if [ ! -f "$venv_dir/pyvenv.cfg" ] || [ ! -x "$venv_python" ]; then
        printf '%s\n' "The environment is incomplete: $venv_dir" \
            'Set FAST_VERIFY_VENV to a new path, or repair the existing environment.' >&2
        exit 1
    fi
    if ! "$venv_python" -c "$version_check"; then
        printf '%s\n' 'The existing environment needs a POSIX Python 3.11 or later.' \
            'Set FAST_VERIFY_VENV to a new path to keep the existing environment.' >&2
        exit 1
    fi
    printf '%s\n' "Using environment: $venv_dir" >&2
else
    python_bin=${FAST_VERIFY_PYTHON:-}
    if [ -n "$python_bin" ]; then
        if ! command -v "$python_bin" >/dev/null 2>&1 || ! "$python_bin" -c "$version_check"; then
            printf '%s\n' 'FAST_VERIFY_PYTHON must select a POSIX Python 3.11 or later.' >&2
            exit 1
        fi
    else
        for candidate in python3 python3.14 python3.13 python3.12 python3.11 python; do
            if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "$version_check" 2>/dev/null; then
                python_bin=$candidate
                break
            fi
        done
        if [ -z "$python_bin" ]; then
            printf '%s\n' 'Install Python 3.11 or later, then run this script again.' \
                'On Linux, install the matching python3-venv package if required.' \
                'On native Windows, use the PowerShell steps in README.md.' >&2
            exit 1
        fi
    fi
    printf '%s\n' "Creating environment: $venv_dir" >&2
    if ! "$python_bin" -m venv "$venv_dir" >&2; then
        printf '%s\n' 'Could not create the environment. Check Python venv support and directory permissions.' >&2
        exit 1
    fi
fi

if ! "$venv_python" -m pip --version >/dev/null 2>&1; then
    "$venv_python" -m ensurepip --upgrade >&2
fi
printf '%s\n' 'Installing Fast Verify Lab...' >&2
"$venv_python" -m pip install --disable-pip-version-check "$project_dir[tui]" >&2
"$venv_python" -c 'import fast_verify_lab' >&2
printf '%s\n' 'Installation complete. Run: sh run.sh' >&2
