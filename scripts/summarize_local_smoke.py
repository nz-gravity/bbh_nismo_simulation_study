#!/usr/bin/env python3
"""Make a portable smoke-test receipt, retaining failed attempts as failures."""
import argparse
import json
import shutil
from pathlib import Path

import numpy as np
from scipy.special import logsumexp
from local_morphnis import digest, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for label in ("primary", "repeat", "strict"):
        root = args.campaign_root / "smoke/event_000" / label
        inv = json.loads((root / "invocation.json").read_text())
        settings = {k: v for k, v in inv["arguments"].items() if k in
            ("event", "nlive", "fit_seed", "seed", "dlogz", "max_iterations", "de_retries", "walk_n_steps")}
        receipt = {"label": label, "settings": settings, "versions": inv["versions"],
            "morphnis_commit": inv["morphnis_commit"], "benchmark_commit": inv["benchmark_commit"],
            "runner_at_invocation_sha256": inv["script_sha256"],
            "validation": json.loads((root / "validation.json").read_text())}
        if (root / "comparison.json").exists():
            data = json.loads((root / "comparison.json").read_text())
            result = root / "nis/result.npz"
            with np.load(result, allow_pickle=False) as arrays:
                independently_summed = float(logsumexp(np.concatenate((arrays["dead_log_weights"], arrays["final_live_log_weights"]))))
                posterior_normalization = float(np.exp(arrays["log_posterior_weights"]).sum())
            if not np.isclose(independently_summed, data["nis"]["log_evidence"], rtol=0, atol=1e-9):
                raise ValueError("Cached quadrature sum mismatch")
            if not np.isclose(posterior_normalization, 1., rtol=0, atol=1e-10):
                raise ValueError("Posterior weights do not normalize")
            for key in ("status", "termination_reason", "likelihood_id", "training", "nis",
                        "delta_logz_nis_reference", "delta_logz_nis_reference_statistical_error",
                        "delta_logz_cheap_reference", "nis_minus_cheap", "posterior_distances",
                        "cost_including_pilot", "limitations"):
                receipt[key] = data[key]
            receipt["cached_quadrature_check"] = {"log_evidence": independently_summed,
                "posterior_weight_sum": posterior_normalization}
            receipt["result_npz_sha256"] = digest(result)
            shutil.copyfile(result, args.output / f"event_000_{label}_result.npz")
            # Original primary's renderer error is preserved, but is not a
            # sampler failure: its saved result and termination are authoritative.
            receipt["initial_renderer_failed"] = (root / "failure.json").exists() or (root / "plot_failure.json").exists()
            if label == "primary":
                receipt["initial_renderer_error"] = "Corner smoothed 1D path rejected density keyword; repaired from cached samples"
                baseline = {"cheap": data["cheap"], "reference": data["reference"]}
                write_new(args.output / "event_000_baselines.json", baseline)
        else:
            failure = json.loads((root / "failure.json").read_text())
            receipt.update({k: failure[k] for k in ("status", "error_type", "error", "seconds", "likelihood_calls")})
            receipt["last_walk"] = failure["recovery_history"][-1]
            receipt["complete_iterations_before_failure"] = receipt["last_walk"]["iteration"]-1
            receipt["failed_walk_attempts"] = sum(not r["succeeded"] for r in failure["recovery_history"])
            receipt["evidence_available"] = False
        write_new(args.output / f"event_000_{label}.json", receipt)
        rows.append(receipt)
    cap = json.loads((args.campaign_root / "safety/max_iterations/comparison.json").read_text())
    if cap["status"] != "non_converged" or cap["termination_reason"] != "max_iterations":
        raise ValueError("Iteration cap was misclassified")
    metadata = json.loads((args.campaign_root / "public_metadata_audit.json").read_text())
    write_new(args.output / "validation_receipt.json", {
        "source_scope": metadata["scope"], "metadata_pairs_passed": metadata["event_count"],
        "cheap_rows": metadata["n_training_rows"],
        "training_rows_range": [metadata["min_training_rows"], metadata["max_training_rows"]],
        "max_abs_noise_evidence_difference": max(abs(e["noise_evidence_difference"]) for e in metadata["events"]),
        "rerun_and_data_guards": json.loads((args.campaign_root / "safety_validation.json").read_text()),
        "cap_test": {"status": cap["status"], "termination_reason": cap["termination_reason"],
            "iterations": cap["nis"]["n_iterations"], "exit_code": 3},
        "original_full_reference_results_available": False,
        "original_frozen_event_ids_available": [0], "scheduler_jobs_submitted": [],
    })
    print(json.dumps([{k: r.get(k) for k in ("label", "status", "nis", "likelihood_calls")} for r in rows], indent=2))


if __name__ == "__main__":
    main()
