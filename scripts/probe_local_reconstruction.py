#!/usr/bin/env python3
"""Probe reproducibility without treating a numerical replay as byte identity."""
import argparse
import json
import sys
from pathlib import Path
from unittest.mock import patch

from local_morphnis import PARAMETERS, audit, digest, load_helpers, read_event, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cheap", type=Path, required=True)
    parser.add_argument("--benchmark-repo", type=Path, required=True)
    parser.add_argument("--nismo-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--events", type=int, nargs="+", default=[0, 48, 99])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(args.benchmark_repo.resolve()))
    from benchmark import injection
    helper = load_helpers(args.nismo_repo / "examples/lvk/morphnis_computation.py")
    checks = []
    for event in args.events:
        _, posterior, expected = read_event(args.cheap, event, "cheap")
        target = args.output / f"event_{event:03d}" / "strain.npz"
        with patch.object(injection, "settings", return_value=expected["scientific_config"]["settings"]):
            actual = injection.generate_data(target)
            likelihood, priors = injection.build_likelihood(target)
        model = helper.build_model(likelihood=likelihood, priors=priors, names=PARAMETERS,
                                   fixed_values=helper.fixed_parameter_values(priors))
        check = {
            "event": event,
            "exact_manifest_fields": {key: actual[key] == expected[key] for key in
                ("scientific_config", "data_sha256", "core_versions", "geometry", "likelihood_id", "noise_log_likelihood")},
            "expected_data_sha256": expected["data_sha256"], "actual_data_sha256": digest(target),
            "posterior_audit": audit(model, posterior, helper, expected["noise_log_likelihood"]),
            "noise_difference": float(likelihood.noise_log_likelihood()-expected["noise_log_likelihood"]),
            "eligible_for_original_data_runner": actual["data_sha256"] == expected["data_sha256"],
        }
        checks.append(check)
        write_new(target.parent / "reconstruction_validation.json", check)
        print(json.dumps(check), flush=True)
    write_new(args.output / "validation.json", checks)


if __name__ == "__main__":
    main()
