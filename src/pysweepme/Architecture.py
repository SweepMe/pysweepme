import sys
from typing import List


class VersionInfo:
    _information_extracted: bool = False
    _python_version_str: str = None
    _python_version_short_str: str = None
    _python_bitness_str: str = None
    _python_suffix: str = None
    _python_compatibility_flags: List[str] = None

    def extract_information(self):
        if not self._information_extracted:
            version = sys.version_info
            self._python_version_str = f"{version.major}.{version.minor}"
            self._python_version_short_str = f"{version.major}{version.minor}"
            self._python_bitness_str = "64" if sys.maxsize > 0x100000000 else "32"
            self._python_suffix = f"{self._python_version_short_str}_{self._python_bitness_str}"
            self._python_compatibility_flags = [
                "any",
                f"any-{self._python_bitness_str}",
                f"{self._python_version_str}-any",
                f"{self._python_version_str}-{self._python_bitness_str}"
            ]

    @property
    def python_version_str(self) -> str:
        if not self._information_extracted:
            self.extract_information()
        return self._python_version_str

    @property
    def python_bitness_str(self) -> str:
        if not self._information_extracted:
            self.extract_information()
        return self._python_bitness_str

    @property
    def python_suffix(self) -> str:
        if not self._information_extracted:
            self.extract_information()
        return self._python_suffix

    @property
    def python_compatibility_flags(self) -> List[str]:
        if not self._information_extracted:
            self.extract_information()
        return self._python_compatibility_flags


version_info = VersionInfo()
