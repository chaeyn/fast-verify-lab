#!/bin/sh
# Run the installed app from any directory. Preserve the caller's config lookup.
set -eu

case "${1-}" in
    -h|--help)
        cat <<'EOF'
Usage: sh run.sh [COMMAND [OPTIONS...]]

No arguments: open the terminal interface.
The first run installs the app into .venv if it is not installed.
Use FAST_VERIFY_VENV to select another environment.
Relative environment paths use the repository root.

Examples:
  sh run.sh
  sh run.sh demo
  sh run.sh setup
  sh run.sh doctor
  sh run.sh tui --provider mock
  sh run.sh ask "What is 17 times 19?" --no-save
  sh run.sh ask --help

After a source update, run sh install.sh to install the new code.
EOF
        exit 0
        ;;
esac

project_dir=$(CDPATH= cd -P "$(dirname "$0")" && pwd)
venv_dir=${FAST_VERIFY_VENV:-"$project_dir/.venv"}
case "$venv_dir" in
    /*) ;;
    *) venv_dir="$project_dir/$venv_dir" ;;
esac
venv_python="$venv_dir/bin/python"
if [ ! -f "$venv_dir/pyvenv.cfg" ] || [ ! -x "$venv_python" ] || \
        ! "$venv_python" -c 'import fast_verify_lab' >/dev/null 2>&1; then
    printf '%s\n' 'The app needs installation. Running install.sh...' >&2
    sh "$project_dir/install.sh" >&2
fi

if [ "$#" -eq 0 ]; then
    set -- tui
fi
exec "$venv_python" -m fast_verify_lab "$@"
