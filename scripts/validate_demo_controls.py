#!/usr/bin/env python3
"""Validate saved demo controls against a preset diagnostic gate and holdout.

This reads immutable results, performs no fits and selects no best seed. Gate
thresholds are diagnostic acceptance criteria, not calibrated statistical tests.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from build_main_results import MainResults, js_divergence, marginal_mass, weighted_correlation, coordinates
from local_morphnis import PARAMETERS, digest, read_event, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text())
    reports, by_event = [], {}
    for path in args.run:
        inv = json.loads((path/"invocation.json").read_text())["arguments"]
        comparison = json.loads((path/"comparison.json").read_text())
        event = inv["event"]
        builder = MainResults(inv["cheap"], inv["reference"], path)
        baseline, reference, reference_mass = builder.baseline(event)
        _, ref, _ = read_event(inv["reference"], event, "reference")
        r = ref[list(PARAMETERS)].to_numpy()
        with np.load(path/"nis/result.npz", allow_pickle=False) as z:
            x = np.concatenate((z["dead_theta"], z["final_live_theta"]))
            w = np.exp(z["log_posterior_weights"])
        specs = baseline["marginal_estimator"]
        masses = {n: marginal_mass(x[:, j], specs[n], w) for j, n in enumerate(PARAMETERS)}
        jsd = {n: js_divergence(masses[n], reference_mass[n]) for n in PARAMETERS}
        corr = float(np.max(abs(weighted_correlation(coordinates(x, r, specs), w)-
                                    weighted_correlation(coordinates(r, r, specs), np.ones(len(r))))))
        nis = comparison["nis"]
        evidence_error = comparison["delta_logz_nis_reference_statistical_error"]
        sigma = abs(comparison["delta_logz_nis_reference"])/evidence_error
        phase = nis.get("morph_phase") or {}
        checks = {
            "stopping": comparison["termination_reason"] in spec["require_termination"],
            "finite_weights": bool(np.isfinite(w).all() and abs(w.sum()-1) < spec["weight_sum_tolerance"]),
            "weight_ess": nis["weight_ess"] >= spec["min_weight_ess"],
            "weight_dominance": float(w.max()) <= spec["max_weight"],
            "mean_marginal_jsd": float(np.mean(list(jsd.values()))) <= spec["max_mean_marginal_jsd_bits"],
            "worst_marginal_jsd": max(jsd.values()) <= spec["max_any_marginal_jsd_bits"],
            "correlations": corr <= spec["max_correlation_difference"],
            "evidence": sigma <= spec["max_evidence_standardized_difference"],
            "retries": not spec["require_zero_retries"] or nis["retry_attempts"] == 0,
            "pool": not spec["require_no_pool_exhaustion"] or phase.get("switch_iteration") is None,
        }
        report = {"event": event, "run": str(path), "passed": all(checks.values()), "checks": checks,
                  "mean_marginal_jsd_bits": float(np.mean(list(jsd.values()))), "marginal_jsd_bits": jsd,
                  "max_correlation_difference": corr, "evidence_standardized_difference": sigma,
                  "delta_logz_reference": comparison["delta_logz_nis_reference"],
                  "max_weight": float(w.max()), "weight_ess": nis["weight_ess"],
                  "retries": nis["retry_attempts"], "morph_phase": phase,
                  "result_sha256": digest(path/"nis/result.npz")}
        reports.append(report)
        by_event.setdefault(event, []).append((report, comparison, masses))
    stability = []
    for event, runs in by_event.items():
        for other in runs[1:]:
            first = runs[0]
            jsd = float(np.mean([js_divergence(first[2][n], other[2][n]) for n in PARAMETERS]))
            error = np.hypot(first[1]["nis"]["log_evidence_err"], other[1]["nis"]["log_evidence_err"])
            sigma = abs(first[1]["nis"]["log_evidence"]-other[1]["nis"]["log_evidence"])/error
            stability.append({"event": event, "mean_marginal_jsd_bits": jsd,
                "evidence_standardized_difference": float(sigma),
                "passed": bool(jsd <= spec["stability_max_mean_marginal_jsd_bits"] and sigma <= spec["stability_max_evidence_standardized_difference"])})
    payload = {"passed": all(r["passed"] for r in reports) and all(s["passed"] for s in stability),
               "runs": reports, "stability": stability, "spec": spec, "spec_sha256": digest(args.spec),
               "limitations": "Marginal and correlation diagnostics do not establish joint coverage or unbiasedness. Heuristic recovery remains explicitly heuristic. Target replay audit is a separate required check."}
    write_new(args.output, payload)
    print(json.dumps(payload, indent=2))
    if not payload["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
