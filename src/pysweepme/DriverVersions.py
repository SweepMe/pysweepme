# The MIT License

# Copyright (c) 2026 SweepMe! GmbH (sweep-me.net)

# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
# of the Software, and to permit persons to whom the Software is furnished to do
# so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Find the driver folder of the driver version that is selected in the SweepMe! Version Manager.

The Version Manager is part of SweepMe! and not of pysweepme. It stores the selected version of each driver in a
versions file 'Version<major>.<minor>.<patch>[dev].ini' inside the VERSIONS folder. This module mirrors the read-only
part of the Version Manager: it reads this file and resolves the folder of the selected driver version, so that a
driver can be loaded with the same version as in SweepMe! without knowing where it is located.
"""

from __future__ import annotations

import configparser
import re
import sqlite3
import sys
from pathlib import Path

from .ErrorMessage import debug
from .FolderManager import get_path

DRIVER_SECTION = "DC"

# Values of the versions file that are no installed versions
DEACTIVATED = "None"
CUSTOM = "custom"
PRE_INSTALLED = "pre-installed"
DEVELOPMENT = "development"
SETTING = "setting"

_VERSIONS_FILE_PATTERN = re.compile(r"^Version(\d+)\.(\d+)\.(\d+)(dev)?\.ini$")


class DriverVersionError(LookupError):
    """The driver folder cannot be determined from the versions file of the Version Manager."""


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_versions_file(version: str | None = None) -> Path:
    """Find the versions file of the Version Manager that belongs to the given pysweepme version.

    Each SweepMe! version has its own versions file. The file is compatible if major and minor version match. The file
    of the same patch version is preferred, otherwise the file with the highest patch version is used, because
    pysweepme is not released with every SweepMe! patch version. The files of a SweepMe! running from source have the
    suffix 'dev', which is used whenever the application is not frozen.

    Args:
        version: The pysweepme version, e.g. '1.6.1.3'. Defaults to the version of the installed pysweepme.

    Returns:
        The path of the versions file. The file itself might be missing if only its backup file exists.

    Raises:
        DriverVersionError: If there is no versions file for the major and minor version.
    """
    if version is None:
        from . import __version__  # noqa: PLC0415  # imported here to avoid a circular import

        version = __version__

    major, minor, patch = (int(part) for part in version.split(".")[0:3])
    dev = not _is_frozen()
    versions_folder = Path(str(get_path("VERSIONS")))

    candidates: dict[int, Path] = {}
    if versions_folder.is_dir():
        for file in versions_folder.iterdir():
            # a versions file whose backup is the only remaining copy is still a candidate
            file_name = file.name.removesuffix(".bak")
            match = _VERSIONS_FILE_PATTERN.match(file_name)
            if not match:
                continue
            if (int(match.group(1)), int(match.group(2))) != (major, minor) or bool(match.group(4)) != dev:
                continue
            candidates[int(match.group(3))] = versions_folder / file_name

    if not candidates:
        suffix = "dev" if dev else ""
        msg = (
            f"No versions file 'Version{major}.{minor}.*{suffix}.ini' found in '{versions_folder}'. "
            f"Start SweepMe! {major}.{minor} once to create it or pass the folder of the driver."
        )
        raise DriverVersionError(msg)

    return candidates.get(patch, candidates[max(candidates)])


def _read_versions_file(versions_file: Path) -> configparser.ConfigParser:
    """Read the versions file and fall back to its backup file like the Version Manager does.

    The file is never written, as it is owned by the Version Manager.
    """
    for file in (versions_file, versions_file.with_name(versions_file.name + ".bak")):
        if not file.is_file():
            continue
        config = configparser.ConfigParser(interpolation=None, strict=False)
        config.optionxform = str  # type: ignore[assignment, method-assign]  # driver names are case-sensitive
        try:
            config.read(file, encoding="utf-8")
        except configparser.Error:
            debug(f"DriverVersions: Cannot read versions file '{file}'.")
            continue
        return config

    msg = f"Cannot read versions file '{versions_file}' or its backup file."
    raise DriverVersionError(msg)


def get_driver_version_entry(name: str, versions_file: Path) -> str:
    """Get the entry of the Version Manager for the given driver.

    The entry is either the key of a source like 'custom' or 'repo', the file id of an installed version, or 'None'
    if the driver is deactivated.

    Args:
        name: The name of the driver.
        versions_file: The versions file of the Version Manager.

    Returns:
        The entry of the driver.

    Raises:
        DriverVersionError: If the driver is not listed in the versions file.
    """
    config = _read_versions_file(versions_file)

    # The Version Manager lists each driver by its id and by its name. pysweepme only knows the name.
    if not config.has_option(DRIVER_SECTION, name):
        # TODO: If a driver is not listed yet, the Version Manager selects a default version in the order custom,
        #  pre-installed, other sources, installed version with the highest file id. This order needs to be added
        #  here, which will be solved automatically when parts of the Version Manager are moved to pysweepme.
        msg = (
            f"Driver '{name}' is not listed in versions file '{versions_file}'. "
            "Open the Version Manager in SweepMe! once or pass the folder of the driver."
        )
        raise DriverVersionError(msg)

    return config.get(DRIVER_SECTION, name).strip()


def _get_installed_folder(name: str, file_id: str) -> Path:
    """Get the folder of an installed driver version, i.e. SHAREDDEVICES/DC_<id>_<file_id>_<name>."""
    shared_devices_folder = Path(str(get_path("SHAREDDEVICES")))
    # TODO: The Version Manager skips installed versions whose files do not match the hash in info.ini. This
    #  integrity check is not done here yet.
    for folder in sorted(shared_devices_folder.glob(f"DC_*_{file_id}_{name}")):
        if (folder / name).is_dir():
            return folder

    msg = f"Installed version {file_id} of driver '{name}' not found in '{shared_devices_folder}'."
    raise DriverVersionError(msg)


def _get_persistent_source_folder(key: str) -> Path:
    """Get the folder of a driver source that is defined in SweepMe!, e.g. 'repo'.

    These sources are added in SweepMe! and stored in the table 'source_directories' of the database CONFIG/info.dat.
    """
    database = Path(str(get_path("CONFIG"))) / "info.dat"
    if database.is_file():
        try:
            # open read-only as the database is owned by SweepMe!
            with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
                row = connection.execute(
                    "SELECT path FROM source_directories WHERE object_type = ? AND scope = ? AND key = ?",
                    ("driver", "persistent", key),
                ).fetchone()
        except sqlite3.Error:
            debug(f"DriverVersions: Cannot read driver sources from '{database}'.")
            row = None
        if row:
            return Path(row[0]).resolve()

    msg = f"Driver source '{key}' is not defined in SweepMe!."
    raise DriverVersionError(msg)


def get_driver_folder(name: str) -> str:
    """Get the folder that contains the driver version that is selected in the Version Manager of SweepMe!.

    Args:
        name: The name of the driver.

    Returns:
        The folder that contains the driver folder, i.e. the folder that can be passed to get_driver().

    Raises:
        DriverVersionError: If the folder cannot be determined.
    """
    name = name.strip(r"\/")
    versions_file = get_versions_file()
    entry = get_driver_version_entry(name, versions_file)

    if entry == DEACTIVATED:
        msg = f"Driver '{name}' is deactivated in the Version Manager ('{versions_file}')."
        raise DriverVersionError(msg)

    if entry in (PRE_INSTALLED, DEVELOPMENT, SETTING):
        msg = (
            f"Driver '{name}' uses the version '{entry}', which is not supported without a folder. "
            "Select another version in the Version Manager or pass the folder of the driver."
        )
        raise DriverVersionError(msg)

    if entry.isdigit():
        folder = _get_installed_folder(name, entry)
    elif entry == CUSTOM:
        folder = Path(str(get_path("CUSTOMDEVICES")))
    else:
        folder = _get_persistent_source_folder(entry)

    if not (folder / name).is_dir():
        msg = f"Driver '{name}' with version '{entry}' not found in '{folder}'."
        raise DriverVersionError(msg)

    debug(f"DriverVersions: Driver '{name}' with version '{entry}' is loaded from '{folder}' ('{versions_file.name}').")
    return str(folder)
