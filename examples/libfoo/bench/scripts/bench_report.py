"""
Write the report of the benchmark
=================================

Writes, from 'artifacts/results.json' and the facts of the target, to the
artifacts of the run's output: 'results.csv', a row per layer and way, its time
per point, its sum and the ratio of its time to C's, and 'report.txt', a table
of the time per point of each layer, in each way, and its ratio to C's, with
the machine and the toolchains it ran on. A ratio is left out where C was not
benchmarked.

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
    """Lines saying what the facts say the target is"""

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
        return row["ns"] / baseline[row["way"]] if row["way"] in baseline else None

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
    lines = [
        f"libfoo: {results['points']} points summed {results['rounds']} times,"
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
    lines += ["", *machine(cijoe.facts.target())]

    report = "\n".join(lines) + "\n"
    (artifacts / "report.txt").write_text(report)
    log.info(report)

    return 0
