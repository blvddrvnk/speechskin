#!/bin/bash
# Get the directory where the script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Install/update dependencies
"$DIR/.venv/bin/python" -m pip install -r "$DIR/requirements.txt" --quiet

# Start the application in the background
"$DIR/.venv/bin/python" "$DIR/speechskin.py" "$@" &
