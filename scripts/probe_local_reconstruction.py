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
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--benchmark-repo", type=Path, required=True)
    parser.add_argument("--nismo-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--events", type=int, nargs="+", default=[0, 48, 99])
    parser.add_argument("--all-cheap-rows", action="store_true")
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
        for key in ("scientific_config", "core_versions", "geometry"):
            if actual[key] != expected[key]:
                raise ValueError(f"Scientific reconstruction mismatch: {key}, event {event}")
        noise_difference = float(likelihood.noise_log_likelihood()-expected["noise_log_likelihood"])
        if abs(noise_difference) > 1e-6:
            raise ValueError(f"Noise-likelihood mismatch: event {event}")
        model = helper.build_model(likelihood=likelihood, priors=priors, names=PARAMETERS,
                                   fixed_values=helper.fixed_parameter_values(priors))
        check = {
            "event": event,
            "exact_manifest_fields": {key: actual[key] == expected[key] for key in
                ("scientific_config", "data_sha256", "core_versions", "geometry", "likelihood_id", "noise_log_likelihood")},
            "expected_data_sha256": expected["data_sha256"], "actual_data_sha256": digest(target),
            "posterior_audit": audit(model, posterior, helper, expected["noise_log_likelihood"],
                                     n_points=len(posterior) if args.all_cheap_rows else 32),
            "noise_difference": noise_difference,
            "eligible_for_original_data_runner": actual["data_sha256"] == expected["data_sha256"],
        }
        if args.reference is not None:
            reference_summary, reference, _ = read_event(args.reference, event, "reference")
            if reference_summary["comparison_audit"]["comparison_likelihood_id"] != expected["likelihood_id"]:
                raise ValueError(f"Reference identity mismatch: event {event}")
            check["reference_holdout_audit"] = audit(model, reference, helper, expected["noise_log_likelihood"])
        check["numerical_contract_passed"] = True
        checks.append(check)
        write_new(target.parent / "reconstruction_validation.json", check)
        print(json.dumps(check), flush=True)
    write_new(args.output / "validation.json", checks)
    write_new(args.output / "summary.json", {
        "event_ids": [row["event"] for row in checks],
        "event_count": len(checks),
        "numerical_contract_passed": all(row["numerical_contract_passed"] for row in checks),
        "original_byte_checksums_matched": sum(row["eligible_for_original_data_runner"] for row in checks),
        "cheap_likelihood_replays": sum(row["posterior_audit"]["n_points"] for row in checks),
        "reference_likelihood_replays": sum(row.get("reference_holdout_audit", {}).get("n_points", 0) for row in checks),
        "max_abs_log_prior_residual": max(audit["max_abs_log_prior_difference"] for row in checks
            for audit in (row["posterior_audit"], row.get("reference_holdout_audit", row["posterior_audit"]))),
        "max_abs_log_likelihood_residual": max(audit["max_abs_log_likelihood_residual"] for row in checks
            for audit in (row["posterior_audit"], row.get("reference_holdout_audit", row["posterior_audit"]))),
        "max_abs_noise_log_likelihood_difference": max(abs(row["noise_difference"]) for row in checks),
        "scope": "Reconstructed local targets; numerical posterior-point contracts, not original strain-byte identity or global equivalence proof",
    })


if __name__ == "__main__":
    main()
