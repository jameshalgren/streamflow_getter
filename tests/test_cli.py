from streamflow_getter.cli import main


def test_main_runs():
    assert main([]) == 0
