#!/bin/sh

# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

# Install what building, testing and documenting yace needs
dnf install -y \
  gcc \
  gcc-c++ \
  make \
  pipx \
  python3 \
  python3-pip \
  tree
