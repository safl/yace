# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
Run the program of each target, and check that they agree
=========================================================

Runs the program of each target in 'bench.targets', one after the other. Each
program prints a JSON line per layer and way, {"target", "way", "ns", "sum"},
where 'ns' is the time per point of the best of 'bench.repeat' runs. The step
fails when a program fails, leaves out a layer or a way, or prints a sum other
than rounds * benchlib.SUM_OF_X. The lines go to 'artifacts/results.json'.

Without 'bench.rounds', the step calibrates the rounds of each program so that
one run of its slowest way takes 'bench.seconds'. With the same rounds for
every program, a run of the C program would be about 300 times shorter than a
run of the Python program.

With 'bench.cpu', taskset pins every program to that core. With 'bench.khz'
too, the step pins the clock of the core through cpufreq for the run, and
fails on a target without cpufreq for the core.

results.json also holds how busy each CPU was while each program ran, as
'runs', and the clock settings, as 'clock'.

Config Arguments
----------------

bench.rounds: how many times each way sums the points (default: calibrated)
bench.seconds: how long a run of a program's slowest way takes (default: 2)
bench.repeat: how many times each way is run, the best kept (default: 1)
bench.workdir: where to build and run (default: 'work' in the run's output)
bench.targets: the targets benchmarked (default: all of them)
bench.cpu: the core every program is pinned to (default: none)
bench.khz: the frequency the core is pinned at, in kHz (default: none)
bench.sudo: what writes to cpufreq runs under (default: 'sudo -n')

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

    rounds, seconds, repeat = benchlib.timing(cijoe)
    core = benchlib.cpu(cijoe)
    khz = cijoe.getconf("bench.khz", None)
    khz = None if khz in (None, "", 0) else int(khz)
    if khz is not None and core is None:
        log.error("bench.khz pins the clock of the core of bench.cpu; give it")
        return errno.EINVAL

    found = benchlib.clock(cijoe, core) if core is not None else {}
    clock = {"cpu": core, "pinned": khz is not None, "khz": khz, "found": found}
    if khz is not None:
        if "scaling_min_freq" not in found:
            log.error(f"no cpufreq for cpu{core}; the clock cannot be pinned")
            return errno.ENOTSUP
        pinned = {"scaling_min_freq": khz, "scaling_max_freq": khz}
        available = f"{benchlib.cpufreq(core)}/scaling_available_governors"
        if "performance" in (benchlib.read(cijoe, available) or "").split():
            pinned["scaling_governor"] = "performance"
        if "boost" in found:
            pinned["boost"] = 0
        if not benchlib.set_clock(cijoe, core, pinned):
            benchlib.set_clock(cijoe, core, found)
            return errno.EIO
    try:
        return measure(cijoe, targets, (rounds, seconds, repeat), core, clock)
    finally:
        if khz is not None and not benchlib.set_clock(cijoe, core, found):
            log.error(f"failed: restoring the clock of cpu{core} to {found}")


def printed(state) -> list:
    """Return the JSON lines that a program printed, parsed"""

    return [
        json.loads(line) for line in state.output().splitlines() if line.startswith("{")
    ]


def calibrate(cijoe, target, seconds):
    """The rounds of 'target' for 'seconds' a run, or None where it failed"""

    rounds = 1000
    while True:
        cmd, cwd = benchlib.run_command(cijoe, target, rounds, 1)
        state = benchlib.run(cijoe, cmd, cwd)
        rows = printed(state) if state else []
        if not rows:
            log.error(f"{target}: the calibration run printed no results")
            return None
        found = benchlib.rounds_for(rows, rounds, seconds)
        if found:
            return found
        rounds *= 10


def measure(cijoe, targets, timing, core, clock):
    fixed, seconds, repeat = timing
    rows, problems, runs, rounds_of = [], [], [], {}
    freq = f"{benchlib.cpufreq(core)}/scaling_cur_freq" if core is not None else None
    for target in targets:
        rounds = fixed or calibrate(cijoe, target, seconds)
        if rounds is None:
            return errno.EIO
        rounds_of[target] = rounds
        expected = rounds * benchlib.SUM_OF_X
        cmd, cwd = benchlib.run_command(cijoe, target, rounds, repeat)
        before = benchlib.stat(cijoe)
        khz_before = benchlib.read(cijoe, freq) if freq else None
        state = benchlib.run(cijoe, cmd, cwd)
        if not state:
            return errno.EIO
        khz_after = benchlib.read(cijoe, freq) if freq else None
        after = benchlib.stat(cijoe)
        load = (
            benchlib.busy(benchlib.ticks(before), benchlib.ticks(after))
            if before and after
            else {}
        )
        others = [v for n, v in load.items() if n != core]
        runs.append(
            {
                "target": target,
                "rounds": rounds,
                "cpu": core,
                "busy": {str(n): round(v, 3) for n, v in load.items()},
                "busy_pinned": round(load[core], 3) if core in load else None,
                "busy_others_max": round(max(others), 3) if others else None,
                "khz_before": int(khz_before) if khz_before else None,
                "khz_after": int(khz_after) if khz_after else None,
            }
        )
        found = printed(state)
        wanted = {
            (name, way)
            for name in benchlib.TARGETS[target]["results"]
            for way in benchlib.WAYS
        }
        got = {(row.get("target"), row.get("way")) for row in found}
        if got != wanted:
            problems.append(f"{target}: printed {sorted(got)}, not {sorted(wanted)}")
        for row in found:
            if row.get("sum") != expected:
                problems.append(f"{row}: the sum is not {expected}")
        rows += found

    if problems:
        log.error("the programs disagree:\n  " + "\n  ".join(problems))
        return errno.EIO

    results = {
        "rounds": rounds_of,
        "seconds": None if fixed else seconds,
        "repeat": repeat,
        "points": benchlib.POINTS,
        "opt": benchlib.OPT,
        "clock": clock,
        "runs": runs,
        "rows": rows,
    }
    artifacts = Path(cijoe.output_path) / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "results.json").write_text(json.dumps(results, indent=2) + "\n")

    return 0
