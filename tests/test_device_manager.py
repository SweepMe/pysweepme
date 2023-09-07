"""Test pysweepme DeviceManager functions."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from pysweepme.DeviceManager import get_driver, get_main_py_path, instantiate_device
from pysweepme.EmptyDeviceClass import EmptyDevice

BITNESS_DISCRIMINATOR = 0x100000000


class CustomDevice(EmptyDevice):
    """Dummy Device Class."""


class TestDeviceManager:
    """Test class for pyweepme DeviceManager functions."""

    def test_get_main_py_path(self) -> None:
        """Test that the correct main.py file depending on architecture is returned."""
        bitness = "64" if sys.maxsize > BITNESS_DISCRIMINATOR else "32"
        version = sys.version_info
        python_version = f"{version.major}{version.minor}"
        specific_exists = True

        def is_file(self: Path) -> bool:
            if self.name == "main.py":
                return True
            if self.name == f"main_{python_version}_{bitness}.py" and specific_exists:
                return True
            return False

        with patch("DeviceManager.Path.is_file", new=is_file):
            path = "C:\\my_dc_dir"
            assert get_main_py_path(path) == f"C:\\my_dc_dir\\main_{python_version}_{bitness}.py"
            specific_exists = False
            assert get_main_py_path(path) == "C:\\my_dc_dir\\main.py"

    def test_instantiate(self) -> None:
        """Test that indeed a device instance is returned."""
        folder = "C:\\search"
        name = "my_device"
        found_path = "C:\\found\\main.py"

        class LoadSource:
            Device = CustomDevice

        with patch("DeviceManager.imp.load_source") as mocked_load_soure, patch(
            "DeviceManager.get_main_py_path",
        ) as mocked_get_main_py_path:
            mocked_load_soure.return_value = LoadSource
            mocked_get_main_py_path.return_value = found_path
            device = instantiate_device(folder, name)
            assert isinstance(device, CustomDevice)
            assert mocked_load_soure.call_count == 1
            assert mocked_load_soure.call_args_list[0].args == (name, found_path)
            assert mocked_get_main_py_path.call_count == 1
            assert mocked_get_main_py_path.call_args_list[0].args == (f"{folder}\\{name}",)

    def test_get_driver(self) -> None:
        """Test that get_driver gets the instance and sets the necessery parameters Device and Port, if applicable."""
        name = "my_device"

        def run_test(folder: str, expected_folder: str, port: str) -> None:
            device = CustomDevice()
            with patch("DeviceManager.instantiate_device") as mocked_instantiate_device:
                device.set_parameters = MagicMock()  # type: ignore[method-assign]
                mocked_instantiate_device.return_value = device
                returned_driver = get_driver(name, folder, port_string=port)
                assert returned_driver is device
                assert mocked_instantiate_device.call_count == 1
                assert mocked_instantiate_device.call_args_list[0].args == (expected_folder, name)
                assert device.set_parameters.call_count == 1
                expected_gui_params = {"Device": name, "Port": port} if port else {"Device": name}
                assert device.set_parameters.call_args_list[0].args == (expected_gui_params,)

        run_test("C:\\my_dc_dir", "C:\\my_dc_dir", "")
        run_test(".", ".", "")
        run_test("", ".", "")
        run_test(".", ".", "COM007")
