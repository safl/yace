# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

import importlib.util
import os
import sys
from pathlib import Path

from tests.conftest import needs_cc

ROOT = Path(__file__).parent.parent


def load():
    spec = importlib.util.spec_from_file_location(
        "survey", ROOT / "toolbox" / "survey" / "survey.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@needs_cc
def test_a_header_is_surveyed_by_its_rules(tmp_path, monkeypatch):
    shim = tmp_path / "bin" / "yace"
    shim.parent.mkdir()
    shim.write_text(
        f"#!{sys.executable}\nimport sys\nfrom yace.cli.yace import main\n"
        "sys.exit(main())\n"
    )
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim.parent}{os.pathsep}{os.environ['PATH']}")
    header = tmp_path / "lib.h"
    header.write_text("/** Documented */\nint lib_a(void);\nint lib_b(void);\n")

    survey = load()
    found = survey.survey_header(header, tmp_path / "out", with_capi=True)
    assert (found.get("failed"), found["entities"]) == (None, 2)
    assert (found["rules"], found["capi"]) == ({"missing-doc": 1}, "ok")

    result = {
        "source": "test",
        "headers": [found],
        "entities": 2,
        "rules": found["rules"],
        "failed": 0,
        "capi_builds": 1,
    }
    text = survey.report({"lib": result}, with_capi=True)
    assert "| missing-doc | 1 | 1 |" in text
    assert "| lib | 1 | 2 | 1 | 0 | 1/1 |" in text
