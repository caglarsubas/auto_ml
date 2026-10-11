#!/bin/sh
set -eu
# No shell evaluation, caller command, mutable config or upstream entrypoint.
if [ "$#" -ne 0 ] || [ "$(id -u)" != 10001 ] || [ "$(id -g)" != 10001 ]; then
    echo private_ingress_identity_or_command_rejected >&2
    exit 1
fi
if [ "$(nginx -v 2>&1)" != 'nginx version: nginx/1.30.5' ]; then
    echo private_ingress_version_rejected >&2
    exit 1
fi
for file in /installation/tls.crt /installation/tls.key; do
    if [ ! -f "$file" ] || [ -L "$file" ] || [ ! -r "$file" ]; then
        echo private_ingress_certificate_required >&2
        exit 1
    fi
done
if [ "$(stat -c %u /installation/tls.key)" != 10001 ] || [ "$(stat -c %a /installation/tls.key)" != 400 ]; then
    echo private_ingress_key_permissions_required >&2
    exit 1
fi
if [ ! -d /run/declarai ] || [ -L /run/declarai ]; then
    echo private_ingress_socket_directory_required >&2
    exit 1
fi
mkdir -p /tmp/client /tmp/proxy
# Native certificate/config validation precedes listening. Error output is
# suppressed here; retain a neutral failure, never private certificate contents.
if ! nginx -t -c /etc/nginx/nginx.conf >/dev/null 2>&1; then
    echo private_ingress_preflight_failed >&2
    exit 1
fi
exec nginx -c /etc/nginx/nginx.conf -g 'daemon off;'
