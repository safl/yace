#!/bin/sh
# Install what documenting yace needs; the C compiler comes with the Xcode tools
tree --version && echo "Installed" || brew install tree
