# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

"""
What the steps of the benchmark share: the targets, how each is built and run,
and where, on the target cijoe runs the steps on.

Everything is built in 'bench.workdir', by default 'work' in the run's output,
which holds a copy of libfoo, 'libfoo/', the library built from it, 'lib/', the
bindings yace generated, 'gen/', and each target's program, 'build/<target>/'.
Its path goes into the commands as it is, so it must hold no spaces.
"""

import logging as log
from pathlib import Path

# examples/libfoo, as this is examples/libfoo/bench/scripts/benchlib.py
LIBFOO = Path(__file__).resolve().parents[2]

# FOO_POINTS_MAX, the points each program adds, with x from 0 up; so each sums
# rounds * SUM_OF_X
POINTS = 8
SUM_OF_X = sum(range(POINTS))

# The targets, in the order they are reported, what yace emits for each, the
# results each prints, and the toolchains it is built with; a toolchain is
# named by the config key of its command and the arguments that print its
# version
TARGETS = {
    "c": {
        "emit": ["capi"],
        "results": ["c"],
        "toolchains": {"cc": "--version"},
    },
    "cpp": {
        "emit": ["capi", "cpp"],
        "results": ["cpp"],
        "toolchains": {"cxx": "--version"},
    },
    "rust": {
        "emit": ["rust"],
        "results": ["rust-raw", "rust-safe"],
        "toolchains": {"rustc": "--version", "cargo": "--version"},
    },
    "zig": {
        "emit": ["zig"],
        "results": ["zig"],
        "toolchains": {"zig": "version"},
    },
    "go": {
        "emit": ["go"],
        "results": ["go"],
        "toolchains": {"go": "version"},
    },
    "python": {
        "emit": ["python"],
        "results": ["python-raw", "python-idiomatic"],
        "toolchains": {"python": "--version"},
    },
    "cython": {
        "emit": ["cython"],
        "results": ["cython-raw", "cython-idiomatic"],
        "toolchains": {
            "python": "--version",
            "cython": "-c 'import Cython; print(\"Cython\", Cython.__version__)'",
        },
    },
}

WAYS = ["calls", "callback"]

# Every program, and libfoo, is built at optimisation level 3, which is what
# Zig's ReleaseFast and Rust's release profile are, for the baseline CPU of the
# architecture, which is what gcc, g++ and rustc build for by default and Zig
# builds for with '-mcpu baseline'. Go's compiler has no level.
OPT = "-O3"

# The commands of the toolchains, by the key of their config, 'bench.<key>'
COMMANDS = {
    "cc": "cc",
    "cxx": "c++",
    "rustc": "rustc",
    "cargo": "cargo",
    "zig": "zig",
    "go": "go",
    "python": "python3",
    "yace": "yace",
}


def command(cijoe, key: str) -> str:
    """The command of a toolchain, 'bench.<key>' or its default; Cython is
    asked of the Python"""

    key = "python" if key == "cython" else key
    return str(cijoe.getconf(f"bench.{key}", COMMANDS[key]))


def targets(cijoe) -> list:
    """The targets 'bench.targets' names, a list or a comma-separated string, in
    the order of TARGETS; raises ValueError naming any it does not know"""

    named = cijoe.getconf("bench.targets", list(TARGETS))
    if isinstance(named, str):
        named = [name.strip() for name in named.split(",") if name.strip()]
    unknown = [name for name in named if name not in TARGETS]
    if unknown:
        raise ValueError(f"bench.targets: unknown {unknown}; known: {list(TARGETS)}")

    return [name for name in TARGETS if name in named]


def workdir(cijoe) -> str:
    """Where the target builds and runs, 'bench.workdir'"""

    return str(cijoe.getconf("bench.workdir", Path(cijoe.output_path) / "work"))


def timing(cijoe) -> tuple:
    """'bench.rounds', None where not given, 'bench.seconds' and 'bench.repeat'"""

    rounds = cijoe.getconf("bench.rounds", None)
    rounds = None if rounds in (None, "", 0) else int(rounds)
    seconds = float(cijoe.getconf("bench.seconds", 2))
    return rounds, seconds, int(cijoe.getconf("bench.repeat", 1))


# A probe whose slowest way sums for less than this, in seconds, is too short
# to calibrate the rounds from: a few ticks of the clock, and the program's
# start-up, would be most of it
PROBE = 0.2


def rounds_for(rows: list, rounds: int, seconds: float):
    """The rounds that make the slowest way of 'rows', what a run of 'rounds'
    printed, sum for 'seconds'; None where that run was too short to tell"""

    slowest = max(row["ns"] for row in rows) * POINTS * rounds / 1e9
    if slowest < PROBE:
        return None
    return max(1, round(rounds * seconds / slowest))


def paths(cijoe) -> dict:
    """The paths in the workdir, and the library as the target's OS names it"""

    # cijoe is imported here, where it runs the step, so that the tests can
    # import the rest without it
    from cijoe.core.tools import family

    work = workdir(cijoe)
    suffix = "dylib" if family(cijoe, cijoe.default_target) == "darwin" else "so"
    return {
        "work": work,
        "src": f"{work}/libfoo",
        "programs": f"{work}/libfoo/bench/programs",
        "libdir": f"{work}/lib",
        "lib": f"{work}/lib/libfoo.{suffix}",
        "gen": f"{work}/gen",
        "build": f"{work}/build",
    }


def build_commands(cijoe, target: str) -> list:
    """The commands, with the directory each runs in, building the program of
    'target' in build/<target>"""

    p = paths(cijoe)
    out = f"{p['build']}/{target}"
    link = f"-L {p['libdir']} -lfoo -Wl,-rpath,{p['libdir']}"
    if target == "c":
        cc = command(cijoe, "cc")
        return [
            (
                f"{cc} -std=c11 -D_DEFAULT_SOURCE {OPT} -I {p['gen']}/capi"
                f" {p['programs']}/c/bench.c {link} -o {out}/bench",
                out,
            )
        ]
    if target == "cpp":
        cxx = command(cijoe, "cxx")
        return [
            (
                f"{cxx} -std=c++20 {OPT} -I {p['gen']}/capi -I {p['gen']}/cpp"
                f" {p['programs']}/cpp/bench.cpp {link} -o {out}/bench",
                out,
            )
        ]
    if target == "rust":
        manifest = (
            '[package]\nname = "bench"\nversion = "0.0.0"\nedition = "2021"\n\n'
            f'[dependencies]\nfoo = {{ path = "{p["gen"]}/rust" }}\n\n'
            f'[[bin]]\nname = "bench"\npath = "{p["programs"]}/rust/bench.rs"\n'
        )
        cargo = command(cijoe, "cargo")
        return [
            (f"cat > Cargo.toml <<'EOF'\n{manifest}EOF", out),
            (
                f"FOO_LIB_DIR={p['libdir']} CARGO_PROFILE_RELEASE_OPT_LEVEL=3"
                f" RUSTFLAGS='-C link-arg=-Wl,-rpath,{p['libdir']}'"
                f" {cargo} build --release --offline --quiet",
                out,
            ),
        ]
    if target == "zig":
        zig = command(cijoe, "zig")
        return [
            (
                f"{zig} build-exe -O ReleaseFast -mcpu baseline --cache-dir {out}/cache"
                f" --global-cache-dir {out}/cache -lc -L {p['libdir']} -lfoo"
                f" -rpath {p['libdir']} --dep foo -Mroot={p['programs']}/zig/bench.zig"
                f" -Mfoo={p['gen']}/zig/foo.zig -femit-bin={out}/bench",
                out,
            )
        ]
    if target == "go":
        go = command(cijoe, "go")
        # The go version is the bindings', which their go.mod says
        version = f"$(sed -n 's/^go //p' {p['gen']}/go/go.mod)"
        manifest = (
            f"module bench\n\ngo {version}\n\nrequire foo v0.0.0\n\n"
            f"replace foo => {p['gen']}/go\n"
        )
        return [
            (f"cat > go.mod <<EOF\n{manifest}EOF", out),
            (f"cp {p['programs']}/go/main.go .", out),
            (
                f"GOFLAGS=-mod=mod GOTOOLCHAIN=local"
                f" CGO_LDFLAGS='-L{p['libdir']} -Wl,-rpath,{p['libdir']}'"
                f" {go} build -buildvcs=false -o bench .",
                out,
            ),
        ]
    if target == "python":
        return []
    if target == "cython":
        python = command(cijoe, "python")
        return [
            (f"cp {p['programs']}/cython/* .", out),
            (
                f"FOO_BINDINGS={p['gen']}/cython FOO_LIBRARY={p['lib']}"
                f" FOO_CFLAGS={OPT} {python} setup.py build_ext --inplace",
                out,
            ),
        ]
    raise ValueError(f"no target({target})")


def cpu(cijoe):
    """The core the programs are pinned to, 'bench.cpu', or None for none"""

    value = cijoe.getconf("bench.cpu", None)
    return None if value in (None, "") else int(value)


def run_command(cijoe, target: str, rounds: int, repeat: int) -> tuple:
    """The command running the program of 'target', pinned to the core of
    'bench.cpu' where given, and the directory it runs in"""

    p = paths(cijoe)
    out = f"{p['build']}/{target}"
    args = f"{rounds} {repeat}"
    python = command(cijoe, "python")
    core = cpu(cijoe)
    pin = f"taskset -c {core} " if core is not None else ""
    if target == "rust":
        return f"{pin}{out}/target/release/bench {args}", out
    if target == "python":
        env = f"PYTHONPATH={p['gen']}/python FOO_LIBRARY={p['lib']}"
        return f"env {env} {pin}{python} {p['programs']}/python/bench.py {args}", out
    if target == "cython":
        return f"{pin}{python} bench.py {args}", out

    return f"{pin}{out}/bench {args}", out


# The first line of /proc/stat per CPU: user, nice, system, idle, iowait, irq,
# softirq and steal, in ticks; idle and iowait are the time not busy
STAT = "grep '^cpu[0-9]' /proc/stat"


def stat(cijoe):
    """The lines of STAT on the target, or None where it has no /proc/stat"""

    err, state = cijoe.run(STAT)
    return None if err else state.output()


def ticks(text: str) -> dict:
    """The busy and the total ticks of each CPU, by its number, of 'text', the
    lines of STAT"""

    found = {}
    for line in text.splitlines():
        name, *values = line.split()
        numbers = [int(v) for v in values[:8]]
        idle = numbers[3] + numbers[4]
        found[int(name[3:])] = (sum(numbers) - idle, sum(numbers))
    return found


def busy(before: dict, after: dict) -> dict:
    """The fraction of the time each CPU was busy between two 'ticks'"""

    found = {}
    for n in sorted(set(before) & set(after)):
        total = after[n][1] - before[n][1]
        found[n] = (after[n][0] - before[n][0]) / total if total else 0.0
    return found


def cpufreq(core: int) -> str:
    return f"/sys/devices/system/cpu/cpu{core}/cpufreq"


BOOST = "/sys/devices/system/cpu/cpufreq/boost"

# What clock() reads of a core's cpufreq
CLOCK = (
    "scaling_driver",
    "scaling_governor",
    "scaling_min_freq",
    "scaling_max_freq",
    "cpuinfo_min_freq",
    "cpuinfo_max_freq",
)


def read(cijoe, path: str):
    """The text of 'path' on the target, or None where it cannot be read"""

    err, state = cijoe.run(f"cat {path}")
    return None if err else state.output().strip()


def clock(cijoe, core: int) -> dict:
    """The frequency settings of 'core', and boost, as the target has them;
    empty where it has no cpufreq"""

    found = {}
    for name in CLOCK:
        value = read(cijoe, f"{cpufreq(core)}/{name}")
        if value is not None:
            found[name] = value
    boost = read(cijoe, BOOST)
    if boost is not None:
        found["boost"] = boost
    return found


def set_clock(cijoe, core: int, settings: dict) -> bool:
    """Write 'settings', of the names clock() gives, to 'core' and boost; the
    governor first, then the bounds in the order that keeps min below max"""

    sudo = str(cijoe.getconf("bench.sudo", "sudo -n"))
    writes = []
    if "boost" in settings:
        writes.append((BOOST, settings["boost"]))
    if "scaling_governor" in settings:
        writes.append(
            (f"{cpufreq(core)}/scaling_governor", settings["scaling_governor"])
        )
    lo, hi = settings.get("scaling_min_freq"), settings.get("scaling_max_freq")
    current = clock(cijoe, core)
    bounds = [("scaling_max_freq", hi), ("scaling_min_freq", lo)]
    if lo is not None and int(lo) <= int(current.get("scaling_max_freq", lo)):
        bounds.reverse()
    writes += [(f"{cpufreq(core)}/{name}", v) for name, v in bounds if v is not None]
    for path, value in writes:
        err, _ = cijoe.run(f"echo {value} | {sudo} tee {path} >/dev/null")
        if err:
            log.error(f"failed: writing {value} to {path}")
            return False
    return True


def run(cijoe, cmd: str, cwd=None):
    """Run 'cmd' on the target; the state, or None when it failed, logged"""

    err, state = cijoe.run(cmd, cwd=cwd)
    if err:
        log.error(
            f"failed: err({err}), cmd({cmd}), cwd({cwd}); see {state.output_fpath}"
        )
        return None

    return state
