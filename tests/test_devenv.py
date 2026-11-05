import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent


def tagged(tmp_path):
    for path in ("toolbox/devenv", "toolbox/pkgs"):
        shutil.copytree(ROOT / path, tmp_path / path)
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)

    def tag():
        script = tmp_path / "toolbox" / "devenv" / "tag.sh"
        return subprocess.run(
            ["bash", str(script)], capture_output=True, text=True, check=True
        ).stdout

    return tag


def test_the_tag_follows_what_the_image_is_built_from(tmp_path):
    tag = tagged(tmp_path)

    first = tag()
    with open(tmp_path / "toolbox" / "devenv" / "Containerfile", "a") as file:
        file.write("# changed, not staged\n")
    second = tag()
    (tmp_path / "toolbox" / "devenv" / "new.sh").write_text("true\n")
    assert len({first, second, tag()}) == 3


def test_the_tag_fails_rather_than_hash_nothing(tmp_path):
    tag = tagged(tmp_path)

    (tmp_path / "toolbox" / "devenv" / "Containerfile").unlink()
    try:
        tag()
    except subprocess.CalledProcessError:
        return
    raise AssertionError("tag.sh gave a tag without its Containerfile")


def test_the_versions_are_those_ci_and_the_crate_name():
    containerfile = (ROOT / "toolbox" / "devenv" / "Containerfile").read_text()
    args = dict(re.findall(r"^ARG (\w+)=(\S+)$", containerfile, re.M))

    cargo = (ROOT / "src/yace/targets/rust/Cargo.toml.template").read_text()
    assert f'rust-version = "{args["RUST_MSRV"]}"' in cargo

    workflow = (ROOT / ".github/workflows/verify_and_publish.yml").read_text()
    assert re.findall(r"^\s+version: (\S+)$", workflow, re.M) == [args["ZIG"]]
    assert re.findall(r"^\s+go-version: (\S+)$", workflow, re.M) == [args["GO"]]


def test_devenv_run_passes_the_command_as_given(tmp_path):
    fake = tmp_path / "container"
    fake.write_text('#!/bin/sh\nwhile [ "$1" != bash ]; do shift; done\nexec "$@"\n')
    fake.chmod(0o755)

    proc = subprocess.run(
        ["make", "-s", "-C", str(ROOT), "devenv-run", f"CONTAINER={fake}"]
        + ["CMD=echo \"it's\" 'a test'"],
        capture_output=True,
        text=True,
    )
    assert proc.stdout == "it's a test\n", proc.stderr
