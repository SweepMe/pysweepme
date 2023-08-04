"""Make sure that the version number has been increased and does not exist on PyPI yet."""

import importlib.metadata
import subprocess

pysweepme_version = importlib.metadata.version("pysweepme")

not_found = False

try:
    subprocess.check_call(
        [  # noqa: S603, S607
            "python",
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--ignore-installed",
            "--dry-run",
            f"pysweepme=={pysweepme_version}",
        ],
    )
except subprocess.SubprocessError:
    not_found = True

if not_found is False:
    exc_msg = (
        f"Version {pysweepme_version} seems to be published already. "
        f"Did you forget to increase the version number in pysweepme/__init__.py?"
    )
    print(f"::error::{exc_msg}")  # noqa: T201
    raise ValueError(exc_msg)
