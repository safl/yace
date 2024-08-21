#!/bin/sh

dnf install -y \
  clang-devel \
  make \
  pipx \
  python3 \
  python3-pip \
  python3-setuptools \
  python3-wheel \
  tree \
  twine

# For yace: C API Target
dnf groupinstall -y "Development Tools"
dnf groupinstall -y "Development Libraries"
dnf install -y \
  clang-tools-extra \
  doxygen \
  graphviz

# This **should** ensure that yace cli is invokable
pipx ensurepath
