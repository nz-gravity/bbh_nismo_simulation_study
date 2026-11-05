"""Scientific boundary checks for the local workflow (run in the pinned env)."""
import importlib.util
import json
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


@pytest.fixture
def reconstruction(tmp_path):
    data = tmp_path / "strain.npz"
    data.write_bytes(b"audited reconstruction test fixture")
    original = {"data_sha256": "original-byte-hash", "likelihood_id": "original-id",
        "scientific_config": {"settings": {"noise_seed": 1}},
        "core_versions": {"bilby": "test"}, "geometry": {"H1": {"length": 4}}}
    actual = original | {"data_sha256": workflow.digest(data), "likelihood_id": "reconstructed-id"}
    data.with_suffix(".json").write_text(json.dumps(actual))
    check = {"n_points": 84, "max_abs_log_prior_difference": 0.,
             "max_abs_log_likelihood_residual": 1e-9, "offset_to_documented_convention_residual": 0.}
    receipt = {"event": 1, "numerical_contract_passed": True,
        "actual_data_sha256": actual["data_sha256"], "expected_data_sha256": original["data_sha256"],
        "posterior_audit": check, "reference_holdout_audit": check | {"n_points": 32}, "noise_difference": 0.}
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt))
    return data, original, path, receipt


def test_reconstruction_requires_explicit_complete_receipt(reconstruction):
    data, original, path, receipt = reconstruction
    with pytest.raises(ValueError, match="original event checksum"):
        workflow.validate_data_origin(data, original, 1, 84)
    _, origin = workflow.validate_data_origin(data, original, 1, 84, path)
    assert origin["kind"] == "validated_reconstruction"
    receipt["posterior_audit"]["n_points"] = 32
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="Incomplete"):
        workflow.validate_data_origin(data, original, 1, 84, path)


def test_reconstruction_rejects_changed_bytes_and_nonfinite_replays(reconstruction):
    data, original, path, receipt = reconstruction
    receipt["reference_holdout_audit"]["max_abs_log_likelihood_residual"] = float("nan")
    path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="replay failed"):
        workflow.validate_data_origin(data, original, 1, 84, path)
    receipt["reference_holdout_audit"]["max_abs_log_likelihood_residual"] = 0.
    path.write_text(json.dumps(receipt))
    data.write_bytes(b"changed after audit")
    with pytest.raises(ValueError, match="checksum mismatch"):
        workflow.validate_data_origin(data, original, 1, 84, path)
