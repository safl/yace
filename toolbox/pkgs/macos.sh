#!/bin/sh

# Install packages via brew, assuming that brew is: installed, updated, and upgraded
clang-format --version && echo "Installed" || brew install clang-format
dot -V && echo "Installed" || brew install graphviz
doxygen --version && echo "Installed" || brew install doxygen
tree --version && echo "Installed" || brew install tree
meson --version && echo "Installed" || brew install meson
