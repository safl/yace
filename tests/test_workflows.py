# SPDX-FileCopyrightText: Simon A. F. Lund <os@safl.dk>
#
# SPDX-License-Identifier: GPL-2.0-only

from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent


def test_the_result_that_main_requires_needs_every_job():
    """main requires ci-result alone, so a job that it does not need would not
    block a merge"""

    path = ROOT / ".github" / "workflows" / "verify_and_publish.yml"
    jobs = yaml.safe_load(path.read_text())["jobs"]
    result = jobs.pop("ci-result")
    assert result["if"] == "always()"
    assert sorted(result["needs"]) == sorted(jobs)
