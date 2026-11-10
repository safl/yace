# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
Runs the Cython benchmark, fast, as built by setup.py beside it:

  python bench.py ROUNDS REPEAT
"""

import sys

import fast

if __name__ == "__main__":
    fast.main(*(int(arg) for arg in sys.argv[1:3]))
