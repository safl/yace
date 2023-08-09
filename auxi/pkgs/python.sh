#!/usr/bin/env bash

# Setup pipx
python3 -m site --user-base
python3 -m pip install --upgrade pip
python3 -m pip install pipx
python3 -m pipx ensurepath

# Install Python-based tools from PyPI via pipx
pipx install black
pipx install coverage
pipx install isort
pipx install kmdo
