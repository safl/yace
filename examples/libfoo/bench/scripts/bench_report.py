# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
Write the report of the benchmark
=================================

Writes 'results.csv' and 'report.txt' to the artifacts of the run's output,
from 'artifacts/results.json' and the facts of the target. Both give the time
per point of each layer and way, and its ratio to the time of C. The report
adds the machine, the toolchains, the optimisation level, the pinning, and how
busy the CPUs were. A ratio is empty where C was not benchmarked or ran in
less than one tick of the clock.

Retargetable: True
------------------
"""

import csv
import errno
import json
import logging as log
from pathlib import Path

import benchlib


def machine(facts) -> list:
    """Return the lines of the report that describe the target, from its facts"""

    memory = facts.get("system.memory_kib")
    lines = [
        "cpu: "
        + ", ".join(
            str(part)
            for part in (
                facts.get("cpu.model"),
                (
                    f"{facts.get('system.cpus')} CPUs"
                    if facts.get("system.cpus")
                    else None
                ),
                f"{memory / 1024 / 1024:.0f} GiB" if memory else None,
            )
            if part
        ),
        "os: "
        + ", ".join(
            part
            for part in (
                facts.get("os.pretty_name"),
                " ".join(
                    str(facts.get(f"kernel.{key}"))
                    for key in ("name", "release", "machine")
                    if facts.get(f"kernel.{key}")
                ),
            )
            if part
        ),
    ]
    for name, version in (facts.get("toolchains") or {}).items():
        lines.append(f"{name}: {version}")

    return lines


def conditions(results) -> list:
    """Lines saying how the programs were built and what they ran on"""

    clock = results.get("clock") or {}
    core, found = clock.get("cpu"), clock.get("found") or {}
    lines = [f"built at {results.get('opt', '?')} for the baseline CPU"]
    if core is None:
        lines.append("not pinned to a core; the clock not pinned")
    elif clock.get("pinned"):
        lines.append(f"pinned to cpu{core}, its clock at {clock['khz']} kHz")
    else:
        driver = found.get("scaling_driver", "no cpufreq")
        lines.append(f"pinned to cpu{core}; the clock not pinned ({driver})")
    for run in results.get("runs", []):
        parts = []
        if run.get("busy_pinned") is not None:
            parts.append(f"cpu{run['cpu']} {run['busy_pinned']:.0%} busy")
        if run.get("busy_others_max") is not None:
            parts.append(f"other CPUs at most {run['busy_others_max']:.0%}")
        if run.get("khz_before") is not None:
            parts.append(f"{run['khz_before']} to {run['khz_after']} kHz")
        lines.append(f"{run['target']}: " + ", ".join(parts))
    return lines


def durations(results) -> list:
    """Return a line per program with its rounds and how long its runs took"""

    rounds = results["rounds"]
    if not isinstance(rounds, dict):
        return []
    lines = []
    for target, count in rounds.items():
        took = [
            row["ns"] * results["points"] * count / 1e9
            for row in results["rows"]
            if row["target"] in benchlib.TARGETS[target]["results"]
        ]
        lines.append(
            f"{target}: {count} rounds, a run of {min(took):.2f} to {max(took):.2f} s"
        )
    return lines


def main(args, cijoe):
    artifacts = Path(cijoe.output_path) / "artifacts"
    path = artifacts / "results.json"
    if not path.exists():
        log.error(f"no results at {path}; run bench_run first")
        return errno.ENOENT
    results = json.loads(path.read_text())

    baseline = {
        row["way"]: row["ns"] for row in results["rows"] if row["target"] == "c"
    }

    def ratio(row):
        # A run shorter than one tick of the clock, as on macOS, gives C a time of 0
        c = baseline.get(row["way"])
        return row["ns"] / c if c else None

    with (artifacts / "results.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["target", "way", "ns", "sum", "ratio_to_c"])
        for row in results["rows"]:
            r = ratio(row)
            writer.writerow(
                [
                    row["target"],
                    row["way"],
                    row["ns"],
                    row["sum"],
                    "" if r is None else f"{r:.2f}",
                ]
            )

    by = {(row["target"], row["way"]): row for row in results["rows"]}
    names = list(dict.fromkeys(row["target"] for row in results["rows"]))
    head = f"{'target':<18}" + "".join(f"{way:>12}{'x C':>8}" for way in benchlib.WAYS)
    rounds = results["rounds"]
    summed = "" if isinstance(rounds, dict) else f" summed {rounds} times"
    lines = [
        f"libfoo: {results['points']} points{summed},"
        f" best of {results['repeat']} runs, ns per point",
        "",
        head,
        "-" * len(head),
    ]
    for name in names:
        line = f"{name:<18}"
        for way in benchlib.WAYS:
            row = by.get((name, way))
            r = ratio(row) if row else None
            line += f"{row['ns']:>12.1f}" if row else f"{'':>12}"
            line += f"{r:>8.1f}" if r is not None else f"{'':>8}"
        lines.append(line)
    lines += ["", *durations(results), *conditions(results)]
    lines += ["", *machine(cijoe.facts.target())]

    report = "\n".join(lines) + "\n"
    (artifacts / "report.txt").write_text(report)
    log.info(report)

    return 0
