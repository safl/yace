#!/usr/bin/env python3
"""
Survey popular C libraries to measure yace parser coverage.

Three library sources:
  packaged.txt  — Debian packages (apt install, parse system headers)
  vendored.txt  — Single-file downloads (header-only / vendored)
  repos.txt     — Git repos to clone (multi-header, non-packaged)

Usage:
    python3 toolbox/survey/survey.py                  # full run
    python3 toolbox/survey/survey.py --skip-download  # reuse cached data
    python3 toolbox/survey/survey.py --report-only    # regenerate report
    python3 toolbox/survey/survey.py --packaged-only  # only packaged libs
    python3 toolbox/survey/survey.py --vendored-only  # only vendored libs
    python3 toolbox/survey/survey.py --repos-only     # only cloned repos
"""
import argparse
import glob as globmod
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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


# ---------------------------------------------------------------------------
# File loaders
# ---------------------------------------------------------------------------

def load_tsv(path: Path, min_cols: int = 2) -> List[List[str]]:
    """Load a TSV file, skipping comments and blank lines."""
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) >= min_cols:
            rows.append(parts)
    return rows


def load_packaged() -> List[Tuple[str, str, str]]:
    """Return [(name, deb_pkg, header_path), ...]."""
    return [(r[0], r[1], r[2]) for r in load_tsv(PACKAGED_FILE, 3)]


def load_vendored() -> List[Tuple[str, str]]:
    """Return [(name, url), ...]."""
    return [(r[0], r[1]) for r in load_tsv(VENDORED_FILE, 2)]


def load_repos() -> List[Tuple[str, str, str, Set[str]]]:
    """Return [(name, git_url, include_glob, excludes), ...]."""
    entries = []
    for r in load_tsv(REPOS_FILE, 3):
        excludes: Set[str] = set()
        if len(r) >= 4:
            excludes = {e.strip() for e in r[3].split(",")}
        entries.append((r[0], r[1], r[2], excludes))
    return entries


# ---------------------------------------------------------------------------
# Download / clone helpers
# ---------------------------------------------------------------------------

def download_headers(entries: List[Tuple[str, str]]) -> None:
    """Download vendored headers, skipping cached ones."""
    HEADERS_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in entries:
        dest = HEADERS_DIR / f"{name}.h"
        if dest.exists() and dest.stat().st_size > 0:
            continue
        print(f"  downloading {name}...", end=" ", flush=True)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "yace-survey/1.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                dest.write_bytes(resp.read())
            print("ok")
        except Exception as e:
            print(f"FAILED: {e}")
            if dest.exists():
                dest.unlink()


def clone_repos(entries: List[Tuple[str, str, str, Set[str]]]) -> None:
    """Shallow-clone repos, skipping cached ones."""
    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    for name, git_url, _, _ in entries:
        dest = REPOS_DIR / name
        if dest.exists() and (dest / ".git").exists():
            continue
        print(f"  cloning {name}...", end=" ", flush=True)
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", git_url, str(dest)],
                capture_output=True, text=True, timeout=120,
            )
            print("ok")
        except Exception as e:
            print(f"FAILED: {e}")


# ---------------------------------------------------------------------------
# Error categorization
# ---------------------------------------------------------------------------

def categorize_error(err_msg: str) -> str:
    """Categorize a .status error line into a short category string."""
    if "unsupported amount of ntokens" in err_msg:
        return "expression_macro"
    if "Unsuported typedef" in err_msg:
        m = re.search(r"Unsuported typedef\(TypeKind\.(\w+)\)", err_msg)
        return f"typedef_{m.group(1).lower()}" if m else "typedef_other"
    if "TYPEDEF_DECL not supported" in err_msg:
        m = re.search(r"TypeKind\.(\w+)", err_msg)
        return f"typedef_decl_{m.group(1).lower()}" if m else "typedef_decl_other"
    if "No support for typedef" in err_msg:
        return "typedef_no_support"
    if "Unhandled TypeKind" in err_msg:
        m = re.search(r"TypeKind\.(\w+)", err_msg)
        return f"unhandled_{m.group(1).lower()}" if m else "unhandled_other"
    if "Unsupported type(TypeKind.CHAR_S)" in err_msg:
        return "unsupported_char"
    if "Unsupported type" in err_msg:
        return "unsupported_type_other"
    if "Failed converting" in err_msg:
        return "alias_macro"
    if "expected FIELD_DECL; got: CursorKind.PACKED_ATTR" in err_msg:
        return "packed_attr"
    if "unexpected 'CursorKind.UNION_DECL'" in err_msg:
        return "anonymous_union"
    if "unexpected 'CursorKind.STRUCT_DECL'" in err_msg:
        return "anonymous_struct"
    return f"other: {err_msg[:60]}"


# ---------------------------------------------------------------------------
# yace runner
# ---------------------------------------------------------------------------

def parse_status_file(status_path: Path) -> Optional[Tuple[int, int, Dict[str, int]]]:
    """Parse a .status file. Returns (parsed, skipped, error_cats) or None."""
    if not status_path.exists():
        return None
    content = status_path.read_text()
    m = re.match(r"Parsed (\d+) entities(?:, skipped (\d+) constructs)?", content)
    if not m:
        return None

    parsed = int(m.group(1))
    skipped = int(m.group(2)) if m.group(2) else 0

    error_cats: Dict[str, int] = {}
    for line in content.split("\n"):
        if "error:" in line:
            err_match = re.search(r"error: (.+)$", line)
            if err_match:
                cat = categorize_error(err_match.group(1).strip())
                error_cats[cat] = error_cats.get(cat, 0) + 1

    return parsed, skipped, error_cats


def run_yace_on_header(header: Path, outdir: Path) -> Dict[str, Any]:
    """Run yace on a single header. Returns result dict."""
    outdir.mkdir(parents=True, exist_ok=True)
    stem = header.stem

    try:
        subprocess.run(
            ["yace", str(header), "--output", str(outdir) + "/"],
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

    status_file = outdir / f"{stem}.status"
    result = parse_status_file(status_file)
    if result is None:
        return {"status": "no_status"}

    parsed, skipped, error_cats = result
    total = parsed + skipped
    return {
        "parsed": parsed,
        "skipped": skipped,
        "total": total,
        "parse_rate": round(parsed / total * 100, 1) if total else 0,
        "errors": error_cats,
        "status": "ok",
    }


# ---------------------------------------------------------------------------
# Survey runners
# ---------------------------------------------------------------------------

def _system_include_dirs() -> List[str]:
    """Return system include directories (base + multiarch)."""
    dirs = ["/usr/include"]
    try:
        arch = subprocess.check_output(
            ["dpkg-architecture", "-qDEB_HOST_MULTIARCH"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        if arch:
            dirs.append(f"/usr/include/{arch}")
    except Exception:
        pass
    return dirs


def _find_system_header(header_path: str) -> Optional[Path]:
    """Find a single header across system include dirs."""
    for d in _system_include_dirs():
        p = Path(d) / header_path
        if p.exists():
            return p
    return None


def _glob_system_headers(header_glob: str) -> List[Path]:
    """Glob for headers across system include dirs."""
    found: List[Path] = []
    for d in _system_include_dirs():
        found.extend(Path(p) for p in globmod.glob(f"{d}/{header_glob}"))
    return sorted(set(found))


def run_packaged_survey(entries: List[Tuple[str, str, str]]) -> Dict[str, Any]:
    """Run yace on system-installed headers from Debian packages."""
    results: Dict[str, Any] = {}

    for name, deb_pkg, header_path in entries:
        # Find the header(s) on the system
        if "*" in header_path:
            # Glob pattern — multi-header package
            headers = _glob_system_headers(header_path)
            if not headers:
                results[name] = {
                    "status": "not_installed",
                    "deb_pkg": deb_pkg,
                }
                print(f"  SKIP  {name} ({deb_pkg} not installed)")
                continue

            total_parsed = 0
            total_skipped = 0
            all_errors: Dict[str, int] = {}
            per_header: List[str] = []
            crashed = 0

            for header in headers:
                hname = header.stem
                outdir = OUTPUT_DIR / f"{name}_pkg" / hname
                result = run_yace_on_header(header, outdir)

                if result["status"] == "ok":
                    total_parsed += result["parsed"]
                    total_skipped += result["skipped"]
                    for cat, count in result["errors"].items():
                        all_errors[cat] = all_errors.get(cat, 0) + count
                    per_header.append(
                        f"{hname}: {result['parsed']}/{result['total']} "
                        f"({result['parse_rate']}%)"
                    )
                else:
                    crashed += 1
                    per_header.append(f"{hname}: {result['status']}")

            total = total_parsed + total_skipped
            results[name] = {
                "parsed": total_parsed,
                "skipped": total_skipped,
                "total": total,
                "parse_rate": round(total_parsed / total * 100, 1) if total else 0,
                "errors": all_errors,
                "status": "ok",
                "source": "packaged",
                "deb_pkg": deb_pkg,
                "headers_count": len(headers),
                "headers_crashed": crashed,
                "per_header": per_header,
            }
            print(
                f"  OK    {name}: {total_parsed}/{total} "
                f"({results[name]['parse_rate']}%) "
                f"[{len(headers)} headers, {crashed} crashed]"
            )
        else:
            # Single header
            header = _find_system_header(header_path)
            if header is None:
                results[name] = {
                    "status": "not_installed",
                    "deb_pkg": deb_pkg,
                }
                print(f"  SKIP  {name} ({deb_pkg} not installed)")
                continue

            outdir = OUTPUT_DIR / f"{name}_pkg"
            result = run_yace_on_header(header, outdir)
            result["source"] = "packaged"
            result["deb_pkg"] = deb_pkg
            results[name] = result

            if result["status"] == "ok":
                print(
                    f"  OK    {name}: {result['parsed']}/{result['total']} "
                    f"({result['parse_rate']}%)"
                )
            else:
                print(f"  CRASH {name}")

    return results


def run_vendored_survey(entries: List[Tuple[str, str]]) -> Dict[str, Any]:
    """Run yace on downloaded single-file headers."""
    results: Dict[str, Any] = {}

    for name, _ in entries:
        header = HEADERS_DIR / f"{name}.h"
        if not header.exists():
            results[name] = {"status": "download_failed"}
            print(f"  SKIP  {name} (not downloaded)")
            continue

        outdir = OUTPUT_DIR / name
        result = run_yace_on_header(header, outdir)
        result["source"] = "vendored"
        results[name] = result

        if result["status"] == "ok":
            print(
                f"  OK    {name}: {result['parsed']}/{result['total']} "
                f"({result['parse_rate']}%)"
            )
        elif result["status"] == "timeout":
            print(f"  TIMEOUT {name}")
        else:
            print(f"  CRASH {name}")

    return results


def run_repo_survey(
    entries: List[Tuple[str, str, str, Set[str]]]
) -> Dict[str, Any]:
    """Run yace on each header in cloned repos, aggregating per-repo."""
    results: Dict[str, Any] = {}

    for name, _, include_glob, excludes in entries:
        repo_dir = REPOS_DIR / name
        if not repo_dir.exists():
            results[name] = {"status": "clone_failed"}
            print(f"  SKIP  {name} (not cloned)")
            continue

        pattern = str(repo_dir / include_glob)
        headers = sorted(
            p for p in (Path(f) for f in globmod.glob(pattern, recursive=True))
            if p.name not in excludes
        )
        if not headers:
            results[name] = {"status": "no_headers", "glob": include_glob}
            print(f"  SKIP  {name} (no headers matched '{include_glob}')")
            continue

        total_parsed = 0
        total_skipped = 0
        all_errors: Dict[str, int] = {}
        per_header: List[str] = []
        crashed = 0

        for header in headers:
            hname = header.stem
            outdir = OUTPUT_DIR / f"{name}_repo" / hname
            result = run_yace_on_header(header, outdir)

            if result["status"] == "ok":
                total_parsed += result["parsed"]
                total_skipped += result["skipped"]
                for cat, count in result["errors"].items():
                    all_errors[cat] = all_errors.get(cat, 0) + count
                per_header.append(
                    f"{hname}: {result['parsed']}/{result['total']} "
                    f"({result['parse_rate']}%)"
                )
            else:
                crashed += 1
                per_header.append(f"{hname}: {result['status']}")

        total = total_parsed + total_skipped
        results[name] = {
            "parsed": total_parsed,
            "skipped": total_skipped,
            "total": total,
            "parse_rate": round(total_parsed / total * 100, 1) if total else 0,
            "errors": all_errors,
            "status": "ok",
            "source": "repo",
            "headers_count": len(headers),
            "headers_crashed": crashed,
            "per_header": per_header,
        }

        print(
            f"  OK    {name}: {total_parsed}/{total} "
            f"({results[name]['parse_rate']}%) "
            f"[{len(headers)} headers, {crashed} crashed]"
        )

    return results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _results_table(
    items: List[Tuple[str, Dict[str, Any]]], show_headers: bool = False
) -> List[str]:
    """Generate a markdown table from sorted result items."""
    lines = []
    if show_headers:
        lines.append(
            "| # | Library | Parsed | Skipped | Total | Rate "
            "| Headers | Top Skip Reason |"
        )
        lines.append(
            "|---|---------|--------|---------|-------|------"
            "|---------|-----------------|"
        )
    else:
        lines.append(
            "| # | Library | Parsed | Skipped | Total | Rate | Top Skip Reason |"
        )
        lines.append("|---|---------|--------|---------|-------|------|-----------------|")

    for i, (name, data) in enumerate(items, 1):
        top_err = ""
        if data.get("errors"):
            top_err = max(data["errors"], key=data["errors"].get)
        cols = (
            f"| {i} | {name} | {data['parsed']} | {data['skipped']} | "
            f"{data['total']} | {data['parse_rate']}%"
        )
        if show_headers:
            hcount = data.get("headers_count", "")
            crashed = data.get("headers_crashed", 0)
            hinfo = str(hcount) if not crashed else f"{hcount} ({crashed} crashed)"
            cols += f" | {hinfo}"
        cols += f" | {top_err} |"
        lines.append(cols)
    return lines


def generate_report(results: Dict[str, Any]) -> str:
    """Generate markdown report from results dict."""
    ok = {k: v for k, v in results.items() if v.get("status") == "ok"}
    failed = {k: v for k, v in results.items() if v.get("status") != "ok"}

    total_parsed = sum(v["parsed"] for v in ok.values())
    total_skipped = sum(v["skipped"] for v in ok.values())
    total_entities = total_parsed + total_skipped
    overall_rate = (
        round(total_parsed / total_entities * 100, 1) if total_entities else 0
    )

    lines: List[str] = []
    lines.append("# C Library Survey — yace Parser Coverage\n")
    lines.append("## Summary\n")
    lines.append(f"- **Libraries tested**: {len(results)}")
    lines.append(f"- **Successfully parsed**: {len(ok)}")
    lines.append(f"- **Crashed / failed**: {len(failed)}")
    lines.append(f"- **Total entities**: {total_entities}")
    lines.append(f"- **Parsed**: {total_parsed}")
    lines.append(f"- **Skipped**: {total_skipped}")
    lines.append(f"- **Overall parse rate**: {overall_rate}%\n")

    # Split by source
    packaged = {k: v for k, v in ok.items() if v.get("source") == "packaged"}
    repos = {k: v for k, v in ok.items() if v.get("source") == "repo"}
    vendored = {
        k: v for k, v in ok.items()
        if v.get("source") not in ("packaged", "repo")
    }

    # Packaged libraries
    if packaged:
        lines.append("## Packaged Libraries (Debian)\n")
        sorted_pkg = sorted(
            packaged.items(), key=lambda x: x[1]["parse_rate"], reverse=True
        )
        multi = [(k, v) for k, v in sorted_pkg if v.get("headers_count")]
        single = [(k, v) for k, v in sorted_pkg if not v.get("headers_count")]

        if single:
            lines.extend(_results_table(single))
            lines.append("")
        if multi:
            lines.extend(_results_table(multi, show_headers=True))
            lines.append("")
            lines.append("### Per-Header Breakdown\n")
            for name, data in multi:
                lines.append(f"**{name}** ({data['headers_count']} headers):\n")
                for h in data.get("per_header", []):
                    lines.append(f"- {h}")
                lines.append("")

    # Cloned repos
    if repos:
        lines.append("## Non-Packaged Repos (cloned)\n")
        sorted_repos = sorted(
            repos.items(), key=lambda x: x[1]["parse_rate"], reverse=True
        )
        lines.extend(_results_table(sorted_repos, show_headers=True))
        lines.append("")
        lines.append("### Per-Header Breakdown\n")
        for name, data in sorted_repos:
            lines.append(f"**{name}** ({data['headers_count']} headers):\n")
            for h in data.get("per_header", []):
                lines.append(f"- {h}")
            lines.append("")

    # Vendored / header-only
    if vendored:
        lines.append("## Vendored / Header-Only Libraries\n")
        sorted_v = sorted(
            vendored.items(), key=lambda x: x[1]["parse_rate"], reverse=True
        )
        lines.extend(_results_table(sorted_v))
        lines.append("")

    # Failed
    if failed:
        lines.append("## Crashed / Failed / Not Installed\n")
        lines.append("| Library | Status | Details |")
        lines.append("|---------|--------|---------|")
        for name, data in sorted(failed.items()):
            status = data.get("status", "unknown")
            detail = data.get("deb_pkg", "")
            if not detail:
                detail = data.get(
                    "stderr", data.get("error", data.get("raw", ""))
                )[:80]
            lines.append(f"| {name} | {status} | {detail} |")
        lines.append("")

    # Aggregate error analysis
    all_errors: Dict[str, int] = {}
    for data in ok.values():
        for cat, count in data.get("errors", {}).items():
            all_errors[cat] = all_errors.get(cat, 0) + count

    broad: Dict[str, int] = {
        "TYPEDEF_USE": 0,
        "TYPEDEF_DECL": 0,
        "EXPRESSION_MACRO": 0,
        "ALIAS_MACRO": 0,
        "UNHANDLED_TYPE": 0,
        "UNSUPPORTED_TYPE": 0,
        "OTHER": 0,
    }
    typedef_detail: Dict[str, int] = {}
    for cat, count in all_errors.items():
        if cat == "expression_macro":
            broad["EXPRESSION_MACRO"] += count
        elif cat == "alias_macro":
            broad["ALIAS_MACRO"] += count
        elif cat.startswith("typedef_decl_"):
            broad["TYPEDEF_DECL"] += count
            typedef_detail[cat] = count
        elif cat == "typedef_no_support":
            broad["TYPEDEF_DECL"] += count
        elif cat.startswith("typedef_"):
            broad["TYPEDEF_USE"] += count
            typedef_detail[cat] = count
        elif cat.startswith("unhandled_"):
            broad["UNHANDLED_TYPE"] += count
        elif cat.startswith("unsupported_"):
            broad["UNSUPPORTED_TYPE"] += count
        else:
            broad["OTHER"] += count

    lines.append("## Error Categories (aggregate)\n")
    lines.append("| Rank | Category | Skipped | % of All |")
    lines.append("|------|----------|---------|----------|")
    total_skips = sum(broad.values())
    for rank, (cat, count) in enumerate(
        sorted(broad.items(), key=lambda x: x[1], reverse=True), 1
    ):
        if count == 0:
            continue
        pct = round(count / total_skips * 100, 1) if total_skips else 0
        lines.append(f"| {rank} | {cat} | {count} | {pct}% |")
    lines.append("")

    if typedef_detail:
        lines.append("## Typedef Detail\n")
        lines.append("| TypeKind | Count |")
        lines.append("|----------|-------|")
        for cat, count in sorted(
            typedef_detail.items(), key=lambda x: x[1], reverse=True
        ):
            lines.append(f"| {cat} | {count} |")
        lines.append("")

    lines.append("## Estimated Coverage Improvement\n")
    lines.append("| Fix | Additional Entities | Cumulative Rate |")
    lines.append("|-----|--------------------|--------------------|")
    cumulative = total_parsed
    fixes = [
        ("typedef struct/record", broad["TYPEDEF_USE"]),
        ("expression macros", broad["EXPRESSION_MACRO"]),
        ("typedef declarations", broad["TYPEDEF_DECL"]),
        ("unhandled types (float/double/etc)", broad["UNHANDLED_TYPE"]),
        ("unsupported types (char)", broad["UNSUPPORTED_TYPE"]),
        ("alias macros", broad["ALIAS_MACRO"]),
    ]
    for fix_name, fix_count in fixes:
        cumulative += fix_count
        rate = round(cumulative / total_entities * 100, 1) if total_entities else 0
        lines.append(f"| + {fix_name} | +{fix_count} | {rate}% |")
    lines.append("")

    report = "\n".join(lines)
    REPORT_FILE.write_text(report)
    print(f"\nReport written to {REPORT_FILE}")
    return report


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Survey C libraries with yace")
    parser.add_argument(
        "--skip-download", action="store_true",
        help="Skip downloading headers and cloning repos (reuse cached)",
    )
    parser.add_argument(
        "--report-only", action="store_true",
        help="Only regenerate report from existing results.json",
    )
    parser.add_argument(
        "--packaged-only", action="store_true",
        help="Only survey packaged (Debian) libraries",
    )
    parser.add_argument(
        "--vendored-only", action="store_true",
        help="Only survey vendored/header-only libraries",
    )
    parser.add_argument(
        "--repos-only", action="store_true",
        help="Only survey cloned repos",
    )
    args = parser.parse_args()

    if args.report_only:
        if not RESULTS_FILE.exists():
            print(f"Error: {RESULTS_FILE} not found. Run full survey first.")
            sys.exit(1)
        results = json.loads(RESULTS_FILE.read_text())
        generate_report(results)
        return

    # Determine which sources to run
    run_all = not (args.packaged_only or args.vendored_only or args.repos_only)

    results: Dict[str, Any] = {}

    if run_all or args.packaged_only:
        pkg_entries = load_packaged()
        if pkg_entries:
            print(f"Loaded {len(pkg_entries)} packaged libraries from {PACKAGED_FILE}")
            print("Running yace on system headers...")
            results.update(run_packaged_survey(pkg_entries))
            print()

    if run_all or args.vendored_only:
        vendored_entries = load_vendored()
        if vendored_entries:
            print(
                f"Loaded {len(vendored_entries)} vendored libraries "
                f"from {VENDORED_FILE}"
            )
            if not args.skip_download:
                print("Downloading headers...")
                download_headers(vendored_entries)
                print()
            print("Running yace on vendored headers...")
            results.update(run_vendored_survey(vendored_entries))
            print()

    if run_all or args.repos_only:
        repo_entries = load_repos()
        if repo_entries:
            print(f"Loaded {len(repo_entries)} repos from {REPOS_FILE}")
            if not args.skip_download:
                print("Cloning repos...")
                clone_repos(repo_entries)
                print()
            print("Running yace on cloned repos...")
            results.update(run_repo_survey(repo_entries))
            print()

    if not results:
        print("No libraries surveyed.")
        return

    RESULTS_FILE.write_text(json.dumps(results, indent=2))
    generate_report(results)

    ok_count = sum(1 for v in results.values() if v.get("status") == "ok")
    fail_count = len(results) - ok_count
    print(f"\nDone: {ok_count} parsed, {fail_count} failed/crashed")


if __name__ == "__main__":
    main()
