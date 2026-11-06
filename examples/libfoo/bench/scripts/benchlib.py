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

from cijoe.core.tools import family

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
        "emit": ["python"],
        "results": ["cython"],
        "toolchains": {
            "python": "--version",
            "cython": "-c 'import Cython; print(\"Cython\", Cython.__version__)'",
        },
    },
}

WAYS = ["calls", "callback"]

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


def rounds_and_repeat(cijoe) -> tuple:
    return int(cijoe.getconf("bench.rounds", 1)), int(cijoe.getconf("bench.repeat", 1))


def paths(cijoe) -> dict:
    """The paths in the workdir, and the library as the target's OS names it"""

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
                f"{cc} -std=c11 -D_DEFAULT_SOURCE -O2 -I {p['gen']}/capi"
                f" {p['programs']}/c/bench.c {link} -o {out}/bench",
                out,
            )
        ]
    if target == "cpp":
        cxx = command(cijoe, "cxx")
        return [
            (
                f"{cxx} -std=c++20 -O2 -I {p['gen']}/capi -I {p['gen']}/cpp"
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
                f"FOO_LIB_DIR={p['libdir']}"
                f" RUSTFLAGS='-C link-arg=-Wl,-rpath,{p['libdir']}'"
                f" {cargo} build --release --offline --quiet",
                out,
            ),
        ]
    if target == "zig":
        zig = command(cijoe, "zig")
        return [
            (
                f"{zig} build-exe -O ReleaseFast --cache-dir {out}/cache"
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
                f"FOO_BINDINGS={p['gen']}/python FOO_LIBRARY={p['lib']}"
                f" {python} setup.py -q build_ext --inplace",
                out,
            ),
        ]
    raise ValueError(f"no target({target})")


def run_command(cijoe, target: str, rounds: int, repeat: int) -> tuple:
    """The command running the program of 'target', and the directory it runs in"""

    p = paths(cijoe)
    out = f"{p['build']}/{target}"
    args = f"{rounds} {repeat}"
    python = command(cijoe, "python")
    if target == "rust":
        return f"{out}/target/release/bench {args}", out
    if target == "python":
        env = f"PYTHONPATH={p['gen']}/python FOO_LIBRARY={p['lib']}"
        return f"{env} {python} {p['programs']}/python/bench.py {args}", out
    if target == "cython":
        return f"{python} bench.py {args}", out

    return f"{out}/bench {args}", out


def run(cijoe, cmd: str, cwd=None):
    """Run 'cmd' on the target; the state, or None when it failed, logged"""

    err, state = cijoe.run(cmd, cwd=cwd)
    if err:
        log.error(
            f"failed: err({err}), cmd({cmd}), cwd({cwd}); see {state.output_fpath}"
        )
        return None

    return state
