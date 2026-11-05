#!/usr/bin/env bash
# Install Go from go.dev, the download checked against the checksum pinned for
# the platform, so a release that changed under its name is not installed.
# usage: install-go.sh <version> <prefix> <sha256 of x86_64> <sha256 of aarch64>
set -euo pipefail

version="$1"
prefix="$2"
case "$(uname -m)" in
  x86_64) arch=amd64 sum="$3" ;;
  aarch64) arch=arm64 sum="$4" ;;
  *) echo "no Go release pinned for $(uname -m)" >&2; exit 1 ;;
esac
tarball="go$version.linux-$arch.tar.gz"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

curl -sSfL -o "$work/$tarball" "https://go.dev/dl/$tarball"
echo "$sum  $work/$tarball" | sha256sum -c --quiet -
mkdir -p "$prefix"
tar -xzf "$work/$tarball" -C "$prefix" --strip-components=1
"$prefix/bin/go" version
