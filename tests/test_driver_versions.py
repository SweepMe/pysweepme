"""Test resolving the driver folder from the versions file of the SweepMe! Version Manager."""

from __future__ import annotations

import sqlite3
import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from pysweepme import DriverVersions
from pysweepme.DeviceManager import get_driver_class
from pysweepme.DriverVersions import DriverVersionError, get_driver_folder, get_versions_file

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

DRIVER = "Logger-MyCompany_MyModel"


@pytest.fixture
def folders(tmp_path: Path) -> Iterator[dict[str, Path]]:
    """Redirect all folders used by DriverVersions to a temporary directory."""
    paths = {key: tmp_path / key for key in ("VERSIONS", "SHAREDDEVICES", "CUSTOMDEVICES", "CONFIG")}
    for path in paths.values():
        path.mkdir()

    def get_path(identifier: str) -> str:
        return str(paths[identifier])

    with patch.object(DriverVersions, "get_path", new=get_path):
        yield paths


@pytest.fixture(params=[True, False], ids=["frozen", "source"])
def frozen(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> bool:
    """Run a test for a frozen application and for an application running from source."""
    if request.param:
        monkeypatch.setattr(sys, "frozen", True, raising=False)
    else:
        monkeypatch.delattr(sys, "frozen", raising=False)
    return bool(request.param)


def write_versions_file(folder: Path, version: str, frozen: bool, drivers: dict[str, str]) -> Path:  # noqa: FBT001
    """Write a versions file like the Version Manager does."""
    suffix = "" if frozen else "dev"
    file = folder / f"Version{version}{suffix}.ini"
    lines = ["[DC]", *(f"{name} = {value}" for name, value in drivers.items()), "", "[MC]", "1 = pre-installed", ""]
    file.write_text("\n".join(lines), encoding="utf-8")
    return file


def create_driver(folder: Path, name: str = DRIVER) -> None:
    """Create a minimal driver folder."""
    (folder / name).mkdir(parents=True)
    main_py = "from pysweepme.EmptyDeviceClass import EmptyDevice\n\n\nclass Device(EmptyDevice):\n    pass\n"
    (folder / name / "main.py").write_text(main_py)


class TestGetVersionsFile:
    """Test finding the versions file matching the pysweepme version."""

    def test_exact_patch_version_preferred(self, folders: dict[str, Path], frozen: bool) -> None:  # noqa: FBT001
        """The versions file of the same patch version is used if it exists."""
        for version in ("1.6.0", "1.6.1", "1.6.3"):
            write_versions_file(folders["VERSIONS"], version, frozen, {})
        expected = "Version1.6.1.ini" if frozen else "Version1.6.1dev.ini"
        assert get_versions_file("1.6.1.3").name == expected

    def test_highest_patch_version_fallback(self, folders: dict[str, Path], frozen: bool) -> None:  # noqa: FBT001
        """Without the same patch version, the highest patch version of the same minor version is used."""
        for version in ("1.5.7", "1.5.8", "1.5.10", "1.6.1"):
            write_versions_file(folders["VERSIONS"], version, frozen, {})
        assert get_versions_file("1.5.6.1").name.startswith("Version1.5.10")

    def test_other_minor_version_incompatible(self, folders: dict[str, Path], frozen: bool) -> None:  # noqa: FBT001
        """Versions files of another minor version are never used."""
        write_versions_file(folders["VERSIONS"], "1.5.8", frozen, {})
        with pytest.raises(DriverVersionError):
            get_versions_file("1.6.1.3")

    def test_dev_file_only_from_source(self, folders: dict[str, Path], frozen: bool) -> None:  # noqa: FBT001
        """A frozen application uses the release file, an application running from source uses the dev file."""
        write_versions_file(folders["VERSIONS"], "1.6.1", not frozen, {})
        with pytest.raises(DriverVersionError):
            get_versions_file("1.6.1.3")

    def test_backup_only(self, folders: dict[str, Path], frozen: bool) -> None:  # noqa: FBT001
        """A versions file of which only the backup exists is found and read from the backup."""
        file = write_versions_file(folders["VERSIONS"], "1.6.1", frozen, {DRIVER: "custom"})
        file.rename(file.with_name(file.name + ".bak"))
        create_driver(folders["CUSTOMDEVICES"])
        assert get_versions_file("1.6.1.3") == file
        with patch.object(DriverVersions, "get_versions_file", return_value=file):
            assert get_driver_folder(DRIVER) == str(folders["CUSTOMDEVICES"])


class TestGetDriverFolder:
    """Test resolving the driver folder from the entry in the versions file."""

    @staticmethod
    def resolve(folders: dict[str, Path], entry: str | None) -> str:
        """Write a versions file with the given entry for the driver and resolve the driver folder."""
        drivers = {} if entry is None else {"42": entry, DRIVER: entry}
        file = write_versions_file(folders["VERSIONS"], "1.6.1", True, drivers)  # noqa: FBT003
        with patch.object(DriverVersions, "get_versions_file", return_value=file):
            return get_driver_folder(DRIVER)

    def test_custom(self, folders: dict[str, Path]) -> None:
        """Custom drivers are loaded from CUSTOMDEVICES."""
        create_driver(folders["CUSTOMDEVICES"])
        assert self.resolve(folders, "custom") == str(folders["CUSTOMDEVICES"])

    def test_installed(self, folders: dict[str, Path]) -> None:
        """Installed drivers are loaded from their DC_<id>_<file_id>_<name> folder in SHAREDDEVICES."""
        create_driver(folders["SHAREDDEVICES"] / f"DC_42_1995_{DRIVER}")
        create_driver(folders["SHAREDDEVICES"] / f"DC_42_1996_{DRIVER}")
        assert self.resolve(folders, "1996") == str(folders["SHAREDDEVICES"] / f"DC_42_1996_{DRIVER}")

    def test_installed_missing(self, folders: dict[str, Path]) -> None:
        """An error is raised if the installed version does not exist."""
        create_driver(folders["SHAREDDEVICES"] / f"DC_42_1995_{DRIVER}")
        with pytest.raises(DriverVersionError, match="1996"):
            self.resolve(folders, "1996")

    def test_repo_from_database(self, folders: dict[str, Path], tmp_path: Path) -> None:
        """Persistent sources are read from the SweepMe! database."""
        repo = tmp_path / "my repo"
        create_driver(repo)
        with sqlite3.connect(folders["CONFIG"] / "info.dat") as connection:
            connection.execute(
                "CREATE TABLE source_directories (object_type VARCHAR, scope VARCHAR, key VARCHAR, "
                "key_order INTEGER, path VARCHAR)",
            )
            connection.execute(
                "INSERT INTO source_directories VALUES ('driver', 'persistent', 'repo', 0, ?)",
                (str(repo),),
            )
        connection.close()
        assert self.resolve(folders, "repo") == str(repo.resolve())

    def test_unknown_source(
        self,
        folders: dict[str, Path],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """An error is raised for a source that is not defined in SweepMe!, SWEEPME_DRIVERS_REPO is not used."""
        repo = tmp_path / "repo"
        create_driver(repo)
        monkeypatch.setenv("SWEEPME_DRIVERS_REPO", str(repo))
        with pytest.raises(DriverVersionError, match="repo"):
            self.resolve(folders, "repo")

    @pytest.mark.parametrize("entry", ["pre-installed", "development", "setting", "None"])
    def test_unsupported(self, folders: dict[str, Path], entry: str) -> None:
        """Pre-installed, development, and setting versions are not supported, deactivated drivers cannot load."""
        with pytest.raises(DriverVersionError):
            self.resolve(folders, entry)

    def test_not_listed(self, folders: dict[str, Path]) -> None:
        """An error is raised if the driver is not listed in the versions file."""
        with pytest.raises(DriverVersionError, match="not listed"):
            self.resolve(folders, None)

    def test_driver_folder_missing(self, folders: dict[str, Path]) -> None:
        """An error is raised if the source does not contain the driver."""
        with pytest.raises(DriverVersionError, match="not found"):
            self.resolve(folders, "custom")


def test_get_driver_class_without_folder(folders: dict[str, Path]) -> None:
    """Without a folder, the driver is loaded from the folder given by the versions file."""
    create_driver(folders["CUSTOMDEVICES"])
    file = write_versions_file(folders["VERSIONS"], "1.6.1", True, {DRIVER: "custom"})  # noqa: FBT003
    with patch.object(DriverVersions, "get_versions_file", return_value=file):
        driver_class = get_driver_class(None, DRIVER)
    assert driver_class.__module__ == DRIVER
