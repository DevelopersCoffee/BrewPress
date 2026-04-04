from brewpress import __version__


def test_version_present() -> None:
    assert __version__ == "1.0.0"
