"""Test functions for the Config module."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from pysweepme.Config import Config, DefaultFileIO
from pysweepme.pysweepme_types import FileIOProtocol


class MyPath:
    """An alternative class for testing that is compatible to Path."""


class TestDefaultFileIO:
    """Tests for checking if the default and registering of custom pathlib.Path()-like classes works."""

    def test_default_behaviour(self) -> None:
        """Test if the standard pathlib.Path() is used without a registered alternative."""
        # make sure there is no custom registered function
        DefaultFileIO.custom_default_file_io = None
        path = DefaultFileIO.default_fileio(".")
        assert isinstance(path, Path)
        assert not isinstance(path, MyPath)

    def test_alternative_default(self) -> None:
        """Test if registering an alternative default for file IO operations works."""

        def get_mypath(_: Path | str) -> FileIOProtocol:
            return cast(FileIOProtocol, MyPath())

        DefaultFileIO.register_custom_default(get_mypath)
        path = DefaultFileIO.default_fileio(".")
        assert isinstance(path, MyPath)

    def test_config_init(self) -> None:
        """Make sure that the Config is using the registered file IO type from the DefaultFileIO class."""
        my_path = cast(FileIOProtocol, MyPath())

        def get_mypath(_: Path | str) -> FileIOProtocol:
            return my_path

        DefaultFileIO.register_custom_default(get_mypath)
        config = Config(".")
        assert config.reader_writer is my_path
