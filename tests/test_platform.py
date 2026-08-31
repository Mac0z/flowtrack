from flowtrack.infrastructure.platform import OperatingSystem, operating_system


def test_platform_names_are_normalized() -> None:
    assert operating_system("darwin") is OperatingSystem.MACOS
    assert operating_system("win32") is OperatingSystem.WINDOWS
    assert operating_system("linux") is OperatingSystem.OTHER

