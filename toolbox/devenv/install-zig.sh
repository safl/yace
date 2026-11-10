#!/usr/bin/env bash

# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

# Install Zig as the Zig Software Foundation asks of automation: from a
# community mirror, with the signature verified, and the file it is for checked,
# since minisign does not. usage: install-zig.sh <version> <prefix>
set -euo pipefail

version="$1"
prefix="$2"
# The foundation's key, from https://ziglang.org/download
key=RWSGOq2NVecA2UPNdBUZykf1CCb147pkmdtYxgb3Ti+JO/wCYvhbAb/U
tarball="zig-$(uname -m)-linux-$version.tar.xz"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

mirrors="$(curl -sSfL https://ziglang.org/download/community-mirrors.txt | shuf || true)"
for mirror in $mirrors "https://ziglang.org/download/$version"; do
  rm -f "$work/$tarball" "$work/$tarball.minisig"
  curl -sSfL -o "$work/$tarball" "$mirror/$tarball?source=yace-container" || continue
  curl -sSfL -o "$work/$tarball.minisig" "$mirror/$tarball.minisig?source=yace-container" || continue
  minisign -Vq -P "$key" -m "$work/$tarball" -x "$work/$tarball.minisig" || continue
  signed="$(sed -n 's/^trusted comment: .*file:\([^[:space:]]*\).*/\1/p' "$work/$tarball.minisig")"
  if [ "$signed" != "$tarball" ]; then
    echo "$mirror: signed for '$signed', not '$tarball'" >&2
    continue
  fi
  mkdir -p "$prefix"
  tar -xJf "$work/$tarball" -C "$prefix" --strip-components=1
  "$prefix/zig" version
  exit 0
done

echo "no mirror served a verified $tarball" >&2
exit 1
