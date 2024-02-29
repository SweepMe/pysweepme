"""Test deprecated decorator."""
import re
from unittest.mock import PropertyMock, patch

from pysweepme._utils import _get_pysweepme_version_tuple, _is_version_reached, deprecated


class TestDeprecated:
    """Test the deprecated decorator."""

    def test_tuple_extract(self) -> None:
        """Test that further version characters and the end are disregarded."""
        assert _get_pysweepme_version_tuple("1.2.3.4-post1") == (1, 2, 3, 4)

    def test_version_compare(self) -> None:
        """Test that version strings are compared semantically."""
        with patch("pysweepme._utils._pysweepme_version", new_callable=PropertyMock(return_value=(1, 2, 3, 4))):
            assert _is_version_reached("1.2") is True
            assert _is_version_reached("1.2.3.3.99") is True
            assert _is_version_reached("1.2.3.4") is True

            assert _is_version_reached("1.2.3.4.1") is False
            assert _is_version_reached("1.3") is False
            assert _is_version_reached("1.11.3.5") is False

    def test_deprecated_decorator_on_function(self) -> None:
        """Test deprecated decorator for simple function."""
        with patch("pysweepme._utils.debug") as mocked_debug:

            @deprecated("1.1", "Do not use.")
            def my_func() -> str:
                return "success"

            assert my_func() == "success"
            assert mocked_debug.call_count == 1
            debug_msg = mocked_debug.call_args_list[0].args[0]
            assert re.search(r"my_func\(\) .* deprecated .* removed .* Do not use\..*", debug_msg)

    def test_deprecated_decorator_on_method(self) -> None:
        """Test deprecated decorator for function of a class."""
        with patch("pysweepme._utils.debug") as mocked_debug:

            class MyClass:
                ret_val = "success"

                @deprecated("1.1", "Do not use.")
                def my_method(self) -> str:
                    return self.ret_val

            assert MyClass().my_method() == "success"
            assert mocked_debug.call_count == 1
            debug_msg = mocked_debug.call_args_list[0].args[0]
            assert re.search(r"my_method\(\) .* deprecated .* removed .* Do not use\..*", debug_msg)

    def test_deprecated_decorator_on_class(self) -> None:
        """Test deprecated decorator for function of a class."""
        with patch("pysweepme._utils.debug") as mocked_debug:

            @deprecated("1.1", "Do not use.")
            class MyClass:
                def __init__(self) -> None:
                    self.check = "success"

            my_class = MyClass()
            assert my_class.check == "success"
            assert mocked_debug.call_count == 1
            debug_msg = mocked_debug.call_args_list[0].args[0]
            assert re.search(r"MyClass\(\) .* deprecated .* removed .* Do not use\..*", debug_msg)
