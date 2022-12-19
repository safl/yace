#!/bin/sh
# Unattended update and upgrade
export DEBIAN_FRONTEND=noninteractive
export DEBIAN_PRIORITY=critical
sudo apt-get -qy update
sudo apt-get -qy \
  -o "Dpkg::Options::=--force-confdef" \
  -o "Dpkg::Options::=--force-confold" upgrade
sudo apt-get -qy autoclean

sudo apt-get -qy install \
  doxygen \
  graphviz \
  clang-format
