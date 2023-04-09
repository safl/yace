#!/bin/sh
# Unattended update and upgrade
export DEBIAN_FRONTEND=noninteractive
export DEBIAN_PRIORITY=critical
apt-get -qy update
apt-get -qy \
  -o "Dpkg::Options::=--force-confdef" \
  -o "Dpkg::Options::=--force-confold" upgrade
apt-get -qy autoclean

# For yace
#
# libclang-dev, required for the ``yace --c-to-yace`` functionality
# pipx, neded by yace-cli / Python venv management for cli-tools, option: required
# make, invoke the various tasks via Makefile, dev-option: optional
# python3-setuptools, building yace dist-package, dev-option: required
# python3-wheel, building yace dist-package, dev-option: required
# twine, required to upload the yace Python package to PyPI via GHA, dev-option: required
# tree, utilized by documentation/kmdo
#
apt-get -qy install \
  libclang-dev \
  make \
  pipx \
  python3 \
  python3-pip \
  python3-setuptools \
  python3-wheel \
  tree \
  twine

# For yace: C API Target
apt-get -qy install \
  build-essential \
  clang-format \
  doxygen \
  graphviz

# This **should** ensure that yace cli is invokable
pipx ensurepath
