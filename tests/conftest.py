import os

import pytest


@pytest.fixture(scope="session")
def dataset_path():
    path = os.environ.get("VERDICT_DATASET")
    if not path:
        pytest.skip("VERDICT_DATASET is not set")
    return path
