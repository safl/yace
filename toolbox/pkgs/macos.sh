#!/bin/sh

# Install packages via brew, assuming that brew is: installed, updated, and upgraded
black --version && echo "Installed" || brew install black
clang-format --version && echo "Installed" || brew install clang-format
dot -V && echo "Installed" || brew install graphviz
doxygen --version && echo "Installed" || brew install doxygen
isort --version && echo "Installed" || brew install isort
tree --version && echo "Installed" || brew install tree
