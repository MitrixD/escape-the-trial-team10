import os
import pathlib

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "dataset: needs the offline dataset (VERDICT_DATASET)")


@pytest.fixture(scope="session")
def dataset_path() -> pathlib.Path:
    value = os.environ.get("VERDICT_DATASET")
    if not value:
        pytest.skip("VERDICT_DATASET is not set")
    return pathlib.Path(value)


@pytest.fixture(scope="session")
def spike_users(dataset_path):
    from tests.helpers import load_spike

    spike = load_spike()
    spike.DATA = str(dataset_path)
    return spike.load()
