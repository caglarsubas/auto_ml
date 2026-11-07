#!/usr/bin/env bash
# Synthetic qualification only. Own a private Linux fixture and leave installed runtimes alone.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
version=20261102.0
case "$(uname -m)" in
  x86_64) pin=3c400f72be459b57b99b1c4f69be96bcd67eef3caf2078e595fc98e688b6b9a3af7802646b3dde7da8a9aba96d34f86be303e0430c7868ab2d13becdd403c0c1 ;;
  aarch64) pin=e829ca32eef36f4e960460a6dcb094d7945ab507e9bfe0275f09467ab9bfeb846528fddfd42349ad64bb4f5b02148e1065c06e573feb8f6a8b3f47efa30a7d2e ;;
  *) echo 'Unsupported synthetic worker architecture' >&2; exit 1 ;;
esac
image='python:3.12.15-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70'
download=$(mktemp -d)
fixture=''
container=''
cleanup() {
  if [[ -n "$container" ]]; then docker rm "$container" >/dev/null; fi
  if [[ -n "$fixture" ]]; then sudo rm -rf -- "$fixture"; fi
  rm -rf -- "$download"
}
trap cleanup EXIT
curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --max-time 90 \
  "https://storage.googleapis.com/gvisor/releases/release/$version/$(uname -m)/gvisor.tar.zstd" \
  --output "$download/gvisor.tar.zstd"
printf '%s  %s\n' "$pin" "$download/gvisor.tar.zstd" | sha512sum --check --status
fixture=$(sudo mktemp -d /var/tmp/declarai-expert-XXXXXXXX)
sudo chmod 0755 "$fixture"
sudo install -d -m 0755 "$fixture/environment/runtime" "$fixture/environment/rootfs"
sudo tar --zstd -xf "$download/gvisor.tar.zstd" -C "$fixture/environment/runtime"
docker pull "$image" >&2
container=$(docker create "$image" true)
docker export "$container" | sudo tar -xf - -C "$fixture/environment/rootfs"
# Give each fixed environment file an independent inode before sealing it.
sudo find "$fixture/environment" -type f -links +1 -exec sh -c '
  for path do
    copy=$(mktemp "$(dirname "$path")/.declarai-copy-XXXXXXXX")
    cp -p -- "$path" "$copy"
    mv -f -- "$copy" "$path"
  done
' sh {} +
sudo install -d -m 0755 "$fixture/environment/rootfs/work"
sudo chown -hR root:root "$fixture/environment"
sudo find "$fixture/environment" \( -type d -o -type f \) -exec chmod a-s,a-t,go-w {} +
sudo /usr/bin/python3 -I -c 'import runpy, sys; sys.path.insert(0, sys.argv.pop(1)); runpy.run_module("qualify_private_expert_worker", run_name="__main__")' "$root/scripts" "$fixture"
