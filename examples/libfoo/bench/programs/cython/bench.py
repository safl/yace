"""
Runs the Cython benchmark, fast, as built by setup.py beside it:

  python bench.py ROUNDS REPEAT
"""

import sys

import fast

if __name__ == "__main__":
    fast.main(*(int(arg) for arg in sys.argv[1:3]))
