#!/usr/bin/env bash
# The image's tag: a digest of what it is built from, as it is on disk
set -euo pipefail
cd "$(dirname "$0")/../.."
git ls-files -z --cached --others --exclude-standard toolbox/devenv toolbox/pkgs/ubuntu.sh \
  | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-16
