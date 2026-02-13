
import pytest

def pytest_addoption(parser):
    parser.addoption(
        "--level2", action="store_true", default=False, help="run level 2 intensive integration tests"
    )

def pytest_collection_modifyitems(config, items):
    if config.getoption("--level2"):
        # --level2 given in cli: do not skip
        return
    skip_level2 = pytest.mark.skip(reason="need --level2 option to run")
    for item in items:
        if "level2" in item.keywords:
            item.add_marker(skip_level2)
