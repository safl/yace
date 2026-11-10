#!/bin/sh

# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

# Install -dev packages for the yace parser coverage survey.
# These are the C libraries listed in toolbox/survey/packaged.txt,
# all available on Debian Trixie.
export DEBIAN_FRONTEND=noninteractive

apt-get -qy update

# Compression
apt-get -qy install \
  zlib1g-dev \
  libbz2-dev \
  liblz4-dev \
  libzstd-dev \
  libbrotli-dev \
  libsnappy-dev \
  liblzo2-dev

# Crypto / Hashing / TLS
apt-get -qy install \
  libmbedtls-dev \
  libssl-dev \
  libgnutls28-dev \
  libsodium-dev \
  nettle-dev \
  libgcrypt20-dev

# Serialization
apt-get -qy install \
  libcjson-dev \
  libjansson-dev \
  libprotobuf-c-dev \
  libmsgpack-c-dev \
  libyaml-dev \
  libexpat1-dev \
  libxml2-dev

# Networking / IO
apt-get -qy install \
  libmosquitto-dev \
  libnanomsg-dev \
  libnng-dev \
  libevent-dev \
  libuv1-dev \
  libcurl4-openssl-dev \
  libssh2-1-dev \
  libssh-dev \
  libzmq3-dev \
  libmicrohttpd-dev \
  libwebsockets-dev

# Database
apt-get -qy install \
  liblmdb-dev \
  libsqlite3-dev \
  libhiredis-dev \
  libpq-dev

# Scripting
apt-get -qy install \
  liblua5.4-dev

# String / Text
apt-get -qy install \
  libutf8proc-dev \
  libcmark-dev \
  libpcre2-dev \
  libonig-dev

# Image / Graphics
apt-get -qy install \
  libpng-dev \
  libjpeg-dev \
  libgif-dev \
  libcairo2-dev \
  libsdl2-dev \
  libdrm-dev \
  libgl-dev \
  libglew-dev

# Audio
apt-get -qy install \
  libao-dev \
  libsndfile1-dev \
  libopus-dev \
  libvorbis-dev

# System / Utility
apt-get -qy install \
  libffi-dev \
  libelf-dev \
  libseccomp-dev \
  libcap-dev \
  libsystemd-dev \
  libudev-dev \
  libbpf-dev

# Math / Science
apt-get -qy install \
  libgsl-dev \
  libfftw3-dev

# Hardware / Embedded
apt-get -qy install \
  libusb-1.0-0-dev \
  libhidapi-dev \
  libgpiod-dev

# Storage
apt-get -qy install \
  libnvme-dev \
  liburing-dev \
  libaio-dev
