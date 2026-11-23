#!/bin/sh
umask 077
cd "$(dirname "$0")" || exit 1
# Terminal may start with a smaller PATH than the operator's interactive shell.
PATH="$PATH:/usr/local/bin:/opt/homebrew/bin"
export PATH
python3 participant.py
result=$?
if [ "$result" -ne 0 ]; then
    printf '\nPress Return to close the review launcher.\n'
    read -r unused
fi
exit "$result"
