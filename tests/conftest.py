import os
import pathlib

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "dataset: needs the offline dataset (VERDICT_DATASET)")


@pytest.fixture
def dataset_path() -> pathlib.Path:
    value = os.environ.get("VERDICT_DATASET")
    if not value:
        pytest.skip("VERDICT_DATASET is not set")
    return pathlib.Path(value)
