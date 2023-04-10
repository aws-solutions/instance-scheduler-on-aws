from instance_scheduler_cli import __version__


def test_version_correctly_picked_up_from_toml():
    assert __version__ == "1.5.0"
