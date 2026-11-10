#!/usr/bin/env python3

# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
Survey C libraries with yace: that it parses any header without failing, and
which rules of the C subset the headers break

Headers written for other purposes are expected to step outside the subset;
that is reported, by rule, not counted against yace. What counts against yace
is failing: a traceback, a timeout, or an 'internal-error' diagnostic. With
'--with-capi', the C API is also generated and checked; for a header outside
the subset that may not build, which is reported but is not a failure of yace.

Three sources of libraries:
  packaged.txt  Debian packages, parsing the installed headers
  vendored.txt  Single-file headers, downloaded
  repos.txt     Git repositories, cloned

Usage:
    python3 toolbox/survey/survey.py --packaged-only --with-capi
    python3 toolbox/survey/survey.py --skip-download --report-only

Exits non-zero when yace failed on any header.
"""

import argparse
import glob as globmod
import json
import re
import subprocess
import sys
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

SCRIPT_DIR = Path(__file__).parent
PACKAGED_FILE = SCRIPT_DIR / "packaged.txt"
VENDORED_FILE = SCRIPT_DIR / "vendored.txt"
REPOS_FILE = SCRIPT_DIR / "repos.txt"
WORK_DIR = Path("/tmp/yace-survey")
HEADERS_DIR = WORK_DIR / "headers"
REPOS_DIR = WORK_DIR / "repos"
OUTPUT_DIR = WORK_DIR / "output"
RESULTS_FILE = WORK_DIR / "results.json"
REPORT_FILE = SCRIPT_DIR / "report.md"

TIMEOUT = 120
STATUS = re.compile(r"^Parsed (\d+) entities, (\d+) diagnostics")
DIAGNOSTIC = re.compile(r"^[^:]*:\d+:\d+: ([a-z-]+): |^<header>: ([a-z-]+): ")


def load_tsv(path: Path, min_cols: int) -> List[List[str]]:
    rows = []
    for line in path.read_text().splitlines() if path.exists() else []:
        line = line.strip()
        if line and not line.startswith("#"):
            parts = [p.strip() for p in line.split("\t")]
            if len(parts) >= min_cols:
                rows.append(parts)
    return rows


def system_include_dirs() -> List[str]:
    dirs = ["/usr/include"]
    try:
        arch = subprocess.check_output(
            ["dpkg-architecture", "-qDEB_HOST_MULTIARCH"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if arch:
            dirs.append(f"/usr/include/{arch}")
    except (OSError, subprocess.CalledProcessError):
        pass
    return dirs


def packaged() -> Dict[str, List[Path]]:
    """The installed headers of each packaged library, by name"""

    found = {}
    for row in load_tsv(PACKAGED_FILE, 3):
        name, pattern = row[0], row[2]
        headers = set()
        for include in system_include_dirs():
            headers.update(Path(p) for p in globmod.glob(f"{include}/{pattern}"))
        found[name] = sorted(headers)
    return found


def vendored(download: bool) -> Dict[str, List[Path]]:
    HEADERS_DIR.mkdir(parents=True, exist_ok=True)
    found = {}
    for name, url, *_ in load_tsv(VENDORED_FILE, 2):
        dest = HEADERS_DIR / f"{name}.h"
        if download and not (dest.exists() and dest.stat().st_size):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "yace-survey"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    dest.write_bytes(resp.read())
            except OSError as exc:
                print(f"  download of {name} failed: {exc}")
        found[name] = [dest] if dest.exists() else []
    return found


def repos(download: bool) -> Dict[str, List[Path]]:
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    found = {}
    for row in load_tsv(REPOS_FILE, 3):
        name, url, pattern = row[0], row[1], row[2]
        excludes = {e.strip() for e in row[3].split(",")} if len(row) > 3 else set()
        dest = REPOS_DIR / name
        if download and not (dest / ".git").exists():
            subprocess.run(
                ["git", "clone", "--depth", "1", url, str(dest)],
                capture_output=True,
                timeout=TIMEOUT,
            )
        found[name] = sorted(
            p
            for p in (
                Path(f) for f in globmod.glob(str(dest / pattern), recursive=True)
            )
            if p.name not in excludes
        )
    return found


def yace(*args) -> Dict[str, Any]:
    """Run yace; 'failed' when it raised or timed out, rather than reported"""

    try:
        proc = subprocess.run(
            ["yace", *map(str, args)], capture_output=True, text=True, timeout=TIMEOUT
        )
    except subprocess.TimeoutExpired:
        return {"failed": "timeout", "returncode": None}
    failed = "traceback" if "Traceback (most recent call last)" in proc.stderr else ""
    return {"failed": failed, "returncode": proc.returncode, "stderr": proc.stderr}


def survey_header(header: Path, outdir: Path, with_capi: bool) -> Dict[str, Any]:
    outdir.mkdir(parents=True, exist_ok=True)
    result: Dict[str, Any] = {"header": str(header)}

    parsed = yace(header, "--output", outdir)
    status = outdir / f"{header.stem}.status"
    if parsed["failed"] or not status.exists():
        result["failed"] = parsed["failed"] or "no status"
        result["stderr"] = parsed.get("stderr", "")[-2000:]
        return result

    lines = status.read_text().splitlines()
    match = STATUS.match(lines[0]) if lines else None
    if not match:
        result["failed"] = "unreadable status"
        return result
    result["entities"] = int(match.group(1))
    rules = Counter()
    for line in lines[1:]:
        found = DIAGNOSTIC.match(line)
        if found:
            rules[found.group(1) or found.group(2)] += 1
    result["rules"] = dict(rules)
    if rules.get("internal-error"):
        result["failed"] = "internal-error"

    if with_capi and not result.get("failed"):
        emitted = yace(
            outdir / f"{header.stem}.yaml",
            "--emit",
            "capi",
            "--output",
            outdir,
            "-I",
            header.parent,
        )
        if emitted["failed"]:
            result["failed"] = f"capi {emitted['failed']}"
        result["capi"] = "ok" if emitted["returncode"] == 0 else "does not build"

    return result


def survey(libraries: Dict[str, List[Path]], source: str, with_capi: bool) -> Dict:
    results = {}
    for name, headers in libraries.items():
        if not headers:
            print(f"  SKIP  {name}: no headers")
            results[name] = {"source": source, "headers": []}
            continue
        per_header = [
            survey_header(h, OUTPUT_DIR / source / name / h.stem, with_capi)
            for h in headers
        ]
        failed = [r for r in per_header if r.get("failed")]
        rules: Counter = Counter()
        for r in per_header:
            rules.update(r.get("rules", {}))
        results[name] = {
            "source": source,
            "headers": per_header,
            "entities": sum(r.get("entities", 0) for r in per_header),
            "rules": dict(rules),
            "failed": len(failed),
            "capi_builds": sum(r.get("capi") == "ok" for r in per_header),
        }
        mark = "FAIL" if failed else "ok"
        print(
            f"  {mark:5} {name}: {len(per_header)} headers,"
            f" {results[name]['entities']} entities, {sum(rules.values())} diagnostics"
        )
    return results


def report(results: Dict[str, Any], with_capi: bool) -> str:
    surveyed = {n: r for n, r in results.items() if r["headers"]}
    headers = sum(len(r["headers"]) for r in surveyed.values())
    failed = {n: r for n, r in surveyed.items() if r["failed"]}
    rules: Counter = Counter()
    for r in surveyed.values():
        rules.update(r["rules"])

    lines = ["# yace survey of C libraries", ""]
    lines += [
        f"- Libraries: {len(surveyed)}, headers: {headers}",
        f"- Headers yace failed on: {sum(r['failed'] for r in surveyed.values())}",
        f"- Entities parsed: {sum(r['entities'] for r in surveyed.values())}",
        f"- Diagnostics: {sum(rules.values())}",
        "",
        "## Diagnostics by rule",
        "",
        "| Rule | Count | Libraries |",
        "|------|-------|-----------|",
    ]
    for rule, count in rules.most_common():
        libs = sum(1 for r in surveyed.values() if rule in r["rules"])
        lines.append(f"| {rule} | {count} | {libs} |")

    lines += ["", "## Libraries", ""]
    header = "| Library | Headers | Entities | Diagnostics | Failed |"
    sep = "|---------|---------|----------|-------------|--------|"
    if with_capi:
        header += " C API builds |"
        sep += "--------------|"
    lines += [header, sep]
    for name, r in sorted(surveyed.items()):
        row = (
            f"| {name} | {len(r['headers'])} | {r['entities']} |"
            f" {sum(r['rules'].values())} | {r['failed']} |"
        )
        if with_capi:
            row += f" {r['capi_builds']}/{len(r['headers'])} |"
        lines.append(row)

    if failed:
        lines += ["", "## Failures of yace", ""]
        for name, r in sorted(failed.items()):
            for h in r["headers"]:
                if h.get("failed"):
                    lines.append(f"- {name}: {Path(h['header']).name}: {h['failed']}")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--packaged-only", action="store_true")
    parser.add_argument("--vendored-only", action="store_true")
    parser.add_argument("--repos-only", action="store_true")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument(
        "--with-capi", action="store_true", help="also generate and check the C API"
    )
    args = parser.parse_args()

    if args.report_only:
        results = json.loads(RESULTS_FILE.read_text())
    else:
        everything = not (args.packaged_only or args.vendored_only or args.repos_only)
        results = {}
        if everything or args.packaged_only:
            print("Packaged libraries")
            results.update(survey(packaged(), "packaged", args.with_capi))
        if everything or args.vendored_only:
            print("Vendored headers")
            download = not args.skip_download
            results.update(survey(vendored(download), "vendored", args.with_capi))
        if everything or args.repos_only:
            print("Repositories")
            download = not args.skip_download
            results.update(survey(repos(download), "repos", args.with_capi))
        WORK_DIR.mkdir(parents=True, exist_ok=True)
        RESULTS_FILE.write_text(json.dumps(results, indent=2))

    REPORT_FILE.write_text(report(results, args.with_capi))
    print(f"Report: {REPORT_FILE}")

    return 1 if any(r.get("failed") for r in results.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
