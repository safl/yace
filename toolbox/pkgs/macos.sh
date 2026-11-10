#!/bin/sh

# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

# Install what documenting yace needs; the C compiler comes with the Xcode tools
tree --version && echo "Installed" || brew install tree
