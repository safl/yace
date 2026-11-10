#!/bin/sh

# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

# Unattended install of what building, testing and documenting yace needs
export DEBIAN_FRONTEND=noninteractive
export DEBIAN_PRIORITY=critical
apt-get -qy update

apt-get -qy install \
  build-essential \
  make \
  pipx \
  python3 \
  python3-pip \
  tree
