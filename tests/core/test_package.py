from filezall_core import __version__


def test_core_package_exports_version() -> None:
    assert __version__ == "0.1.0"
