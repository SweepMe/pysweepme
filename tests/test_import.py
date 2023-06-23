"""Verify that pysweepme import does not already initialize instances."""

import sys


def test_import() -> None:
    """Verify that pysweepme import does not have side-effects.

    When importing pysweepme, it often happened that pysweepme itself already initializes e.g. the FolderManager.
    Then it is no longer possible to define a multi-instance ID that modifies certain folders.
    This test shall make sure, that an import of pysweepme does not initialize the FolderManager yet.
    """
    # the test only works if pysweepme was not imported before
    assert "pysweepme" not in sys.modules, "pysweepme was already imported before running the test"
    import pysweepme

    assert "pysweepme" in sys.modules, "pysweepme could not be imported successfully"
    assert (
        pysweepme.FolderManager.FolderManager.has_instance() is False
    ), "Import of pysweepme has already initialized the FolderManager, preventing multi-instance mode."
