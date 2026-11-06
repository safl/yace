"""
Run the program of each target, and check that they agree
=========================================================

Runs the program of each target in 'bench.targets', one after the other, each
summing the x of the points of a handle 'bench.rounds' times over, in each way,
the best of 'bench.repeat' runs. Each prints a JSON line per layer and way,
{"target", "way", "ns", "sum"}, 'ns' the time per point. Fails when a program
fails, when one leaves out a layer or way, or when a sum is not the one every
program must get. Writes what they printed to 'artifacts/results.json' in the
run's output, with the rounds and repeat.

Config Arguments
----------------

bench.rounds: how many times each way sums the points (default: 1)
bench.repeat: how many times each way is run, the best kept (default: 1)
bench.workdir: where to build and run (default: 'work' in the run's output)
bench.targets: the targets benchmarked (default: all of them)

Retargetable: True
------------------
"""

import errno
import json
import logging as log
from pathlib import Path

import benchlib


def main(args, cijoe):
    try:
        targets = benchlib.targets(cijoe)
    except ValueError as exc:
        log.error(str(exc))
        return errno.EINVAL

    rounds, repeat = benchlib.rounds_and_repeat(cijoe)
    expected = rounds * benchlib.SUM_OF_X
    rows, problems = [], []
    for target in targets:
        cmd, cwd = benchlib.run_command(cijoe, target, rounds, repeat)
        state = benchlib.run(cijoe, cmd, cwd)
        if not state:
            return errno.EIO
        printed = [
            json.loads(line)
            for line in state.output().splitlines()
            if line.startswith("{")
        ]
        wanted = {
            (name, way)
            for name in benchlib.TARGETS[target]["results"]
            for way in benchlib.WAYS
        }
        got = {(row.get("target"), row.get("way")) for row in printed}
        if got != wanted:
            problems.append(f"{target}: printed {sorted(got)}, not {sorted(wanted)}")
        for row in printed:
            if row.get("sum") != expected:
                problems.append(f"{row}: the sum is not {expected}")
        rows += printed

    if problems:
        log.error("the programs disagree:\n  " + "\n  ".join(problems))
        return errno.EIO

    results = {
        "rounds": rounds,
        "repeat": repeat,
        "points": benchlib.POINTS,
        "rows": rows,
    }
    artifacts = Path(cijoe.output_path) / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "results.json").write_text(json.dumps(results, indent=2) + "\n")

    return 0
