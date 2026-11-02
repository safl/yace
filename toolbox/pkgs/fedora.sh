#!/bin/sh
# Install what building, testing and documenting yace needs
dnf install -y \
  gcc \
  gcc-c++ \
  make \
  pipx \
  python3 \
  python3-pip \
  tree
