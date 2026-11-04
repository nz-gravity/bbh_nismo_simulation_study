"""Scientific boundary checks for the local workflow (run in the pinned env)."""
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from morphnis import Model

SCRIPT = Path(__file__).parents[1] / "scripts/local_morphnis.py"
spec = importlib.util.spec_from_file_location("local_morphnis", SCRIPT)
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


@pytest.fixture
def contract():
    nismo = Path(__file__).parents[2] / "nismo-dev"
    helper = workflow.load_helpers(nismo / "examples/lvk/morphnis_computation.py")
    data = np.arange(40, dtype=float).reshape(5, 8)
    posterior = pd.DataFrame(data, columns=workflow.PARAMETERS)
    posterior["log_prior"] = 0.
    posterior["log_likelihood"] = data.sum(axis=1)
    model = Model(workflow.PARAMETERS, lambda x: float(x.sum()), lambda x: 0.)
    return helper, posterior, model


def test_only_documented_likelihood_constants_are_accepted(contract):
    helper, posterior, model = contract
    assert workflow.audit(model, posterior, helper, -100)["log_likelihood_offset"] == 0
    posterior["log_likelihood"] += 100
    assert workflow.audit(model, posterior, helper, -100)["log_likelihood_offset"] == -100
    posterior["log_likelihood"] += 7
    with pytest.raises(ValueError, match="Scientific"):
        workflow.audit(model, posterior, helper, -100)


def test_point_dependent_likelihood_error_is_rejected(contract):
    helper, posterior, model = contract
    posterior.loc[2, "log_likelihood"] += .01
    with pytest.raises(ValueError, match="Scientific"):
        workflow.audit(model, posterior, helper, -100)


def test_records_are_exclusively_created(tmp_path):
    path = tmp_path / "record.json"
    workflow.write_new(path, {"status": "original"})
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        workflow.write_new(path, {"status": "replacement"})
    assert path.read_bytes() == original


def test_all_row_audit_checks_points_between_the_spread_subset(contract):
    helper, _, model = contract
    data = np.arange(128*8, dtype=float).reshape(128, 8)
    posterior = pd.DataFrame(data, columns=workflow.PARAMETERS)
    posterior["log_prior"] = 0.
    posterior["log_likelihood"] = data.sum(axis=1)
    assert 1 not in np.linspace(0, 127, 32, dtype=int)
    posterior.loc[1, "log_likelihood"] += .01
    workflow.audit(model, posterior, helper, -100)
    with pytest.raises(ValueError, match="Scientific"):
        workflow.audit(model, posterior, helper, -100, n_points=len(posterior))
