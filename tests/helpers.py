import importlib.util
import pathlib
import sys


def load_spike():
    path = pathlib.Path(__file__).resolve().parent.parent / "eval" / "ab_verdict_eval.py"
    spec = importlib.util.spec_from_file_location("spike", path)
    module = importlib.util.module_from_spec(spec)
    saved, sys.argv = sys.argv, ["spike"]
    try:
        spec.loader.exec_module(module)
    finally:
        sys.argv = saved
    module.DATA = "unused"
    module.HORIZON = 60
    return module
