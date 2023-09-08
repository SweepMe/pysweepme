"""Test function of the EmptyDevice class."""
from copy import deepcopy
from typing import Any
from unittest.mock import patch

import pytest

from pysweepme.EmptyDeviceClass import EmptyDevice

default_params: dict[str, Any] = {
    "x": 1,
    "y": 2,
}

special_params: dict[str, Any] = {
    "x": 5,
    "y": 8,
}


class CustomDevice(EmptyDevice):
    """Dummy Device Class."""

    passed_parameters: dict[str, Any]

    def __init__(self, default_params: dict[str, Any]) -> None:
        """Save the passed default_params for later use."""
        super().__init__()
        self.default_params = deepcopy(default_params)

    def set_GUIparameter(self) -> dict[str, Any]:  # noqa: N802
        """Return the default params of the DC."""
        return self.default_params

    def get_GUIparameter(self, parameter: dict[str, Any]) -> None:  # noqa: N802
        """Simulate to work with the passed parameters. Instead just save them to a instance variable."""
        self.passed_parameters = parameter


class TestResetLatestParameters:
    """Tests for the reset_latest_parameters function."""

    def setup_method(self) -> None:
        """Prepare a dummy device instance for all tests."""
        self.device = CustomDevice(default_params)

    def test_vanilla(self) -> None:
        """Test initializing the internally saved parameters for the first time."""
        # at the beginning, parameters are not set yet
        assert self.device._latest_parameters is None
        self.device.reset_latest_parameters()
        assert self.device._latest_parameters == default_params

    def test_reset_values(self) -> None:
        """Test resetting internally saved parameters after already being present."""
        self.device._latest_parameters = special_params
        self.device.reset_latest_parameters()
        assert self.device._latest_parameters == default_params

    def test_reset_keeps_device_and_port(self) -> None:
        """Test that resetting parameters keeps the device/port properties."""
        name = "MySuperDevice"
        self.device._latest_parameters = {**special_params, "Device": name}
        self.device.reset_latest_parameters()
        assert self.device._latest_parameters == {**default_params, "Device": name}

        port = "COM007"
        self.device._latest_parameters = {**special_params, "Port": port}
        self.device.reset_latest_parameters()
        assert self.device._latest_parameters == {**default_params, "Port": port}

    def test_list_defaults(self) -> None:
        """Test that the first element is selected for list parameters."""
        self.device.default_params = {
            **default_params,
            "listproperty": ["first", "second", "third"],
        }
        self.device.reset_latest_parameters()
        assert self.device._latest_parameters == {
            **default_params,
            "listproperty": "first",
        }


class TestGetParameters:
    """Tests for the get_parameters function."""

    def setup_method(self) -> None:
        """Prepare a dummy device instance for all tests."""
        self.device = CustomDevice(default_params)

    def test_vanilla(self) -> None:
        """Test that calling the function initializes the latest_parameters."""
        # at the beginning, parameters are not set yet
        with patch.object(
            self.device,
            "reset_latest_parameters",
            wraps=self.device.reset_latest_parameters,
        ) as mocked_function:
            assert self.device._latest_parameters is None
            params = self.device.get_parameters()
            assert self.device._latest_parameters == default_params
            assert params == default_params
            assert mocked_function.call_count == 1

    def test_existing_parameters(self) -> None:
        """Test that existing latest_parameters are not reset when calling get."""
        with patch.object(
            self.device,
            "reset_latest_parameters",
            wraps=self.device.reset_latest_parameters,
        ) as mocked_function:
            self.device._latest_parameters = special_params
            params = self.device.get_parameters()
            assert self.device._latest_parameters == special_params
            assert params == special_params
            assert mocked_function.call_count == 0


class TestSetParameters:
    """Tests for the set_parameters function."""

    def setup_method(self) -> None:
        """Prepare a dummy device instance for all tests."""
        self.device = CustomDevice(default_params)

    def test_with_port(self) -> None:
        """Test that calling the function initializes the latest_parameters and sets the provided port."""
        # at the beginning, parameters are not set yet
        assert self.device._latest_parameters is None
        port = "COM007"
        self.device.set_parameters({"Port": port})
        assert self.device._latest_parameters == {**default_params, "Port": port}

    def test_with_value(self) -> None:
        """Test that calling the function with one of the keys of the default but a different value."""
        assert self.device._latest_parameters is None
        self.device.set_parameters({"x": 99})
        assert self.device._latest_parameters == {"x": 99, "y": default_params["y"]}

    def test_overwrite_partial_parameters(self) -> None:
        """Test that setting some parameters does not reset others."""
        self.device._latest_parameters = special_params
        self.device.set_parameters({"x": 99})
        assert self.device._latest_parameters == {"x": 99, "y": special_params["y"]}

    def test_without_argument(self) -> None:
        """Test that the function just initialized parameters when called without arguments."""
        assert self.device._latest_parameters is None
        self.device.set_parameters()
        assert self.device._latest_parameters == default_params

    def test_unsupported_parameters(self) -> None:
        """Test that an exception is raised when an unsupported parameter is passed."""
        with pytest.raises(ValueError, match=r".* 'nonsense' not supported .*"):
            self.device.set_parameters({"nonsense": 42})
