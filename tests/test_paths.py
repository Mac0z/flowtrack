from pathlib import Path, PureWindowsPath

from flowtrack.infrastructure.paths import application_data_directory, log_directory


def test_macos_application_data_directory() -> None:
    home = Path("/Users/tester")
    assert application_data_directory(platform_name="darwin", home=home) == (
        home / "Library" / "Application Support" / "FlowTrack"
    )


def test_windows_prefers_local_app_data() -> None:
    result = application_data_directory(
        platform_name="win32",
        environment={"LOCALAPPDATA": r"C:\Users\tester\AppData\Local"},
        home=Path("unused"),
    )
    assert PureWindowsPath(result) == PureWindowsPath(
        r"C:\Users\tester\AppData\Local\FlowTrack"
    )


def test_windows_has_home_directory_fallback() -> None:
    home = Path("C:/Users/tester")
    assert application_data_directory(
        platform_name="win32", environment={}, home=home
    ) == home / "AppData" / "Local" / "FlowTrack"


def test_linux_development_path_honors_xdg() -> None:
    assert application_data_directory(
        platform_name="linux", environment={"XDG_DATA_HOME": "/tmp/xdg"}
    ) == Path("/tmp/xdg/flowtrack")


def test_log_directory_is_below_application_data() -> None:
    home = Path("/Users/tester")
    assert log_directory(platform_name="darwin", home=home).parent == (
        application_data_directory(platform_name="darwin", home=home)
    )

