#!/usr/bin/env python3
"""Replay all positive-weight points and audit saved NIS density/weight identities."""
import argparse
import json
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np

from local_morphnis import PARAMETERS, digest, load_helpers, read_event, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--event", type=int, action="append", required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Audit output already exists")
    reports = []
    for event in args.event:
        receipt_path = args.campaign/"outcomes"/f"event_{event:03d}.json"
        receipt = json.loads(receipt_path.read_text())
        out = Path(receipt["output"])
        inv = json.loads((out/"invocation.json").read_text())["arguments"]
        sys.path.insert(0, str(Path(inv["nismo_repo"])/"src"))
        sys.path.insert(0, inv["benchmark_repo"])
        from benchmark import injection
        from morphnis import MorphImportance, NISResult
        _, training, manifest = read_event(inv["cheap"], event, "cheap")
        result = NISResult.load(out/"nis")
        w = result.posterior_weights
        positive = w > 0
        proposal = MorphImportance.fit(training[list(PARAMETERS)].to_numpy(),
            parameter_names=PARAMETERS, seed=inv["fit_seed"], thin=1)
        arrays = {name: np.concatenate((getattr(result, "dead_"+name),
                                        getattr(result, "final_live_"+name)))
                  for name in ("log_q", "log_likelihood", "log_prior", "log_psi", "log_weights")}
        with patch.object(injection, "settings", return_value=manifest["scientific_config"]["settings"]):
            likelihood, priors = injection.build_likelihood(Path(inv["data"]))
        h = load_helpers(Path(inv["nismo_repo"])/"examples/lvk/morphnis_computation.py")
        model = h.build_model(likelihood=likelihood, priors=priors, names=PARAMETERS,
                              fixed_values=h.fixed_parameter_values(priors))
        theta = result.samples[positive]
        replay = {"log_q": proposal.log_prob(theta),
                  "log_likelihood": np.array([model.log_likelihood(t) for t in theta]),
                  "log_prior": np.array([model.log_prior(t) for t in theta])}
        residuals = {name: float(np.max(abs(values-arrays[name][positive])))
                     for name, values in replay.items()}
        identity = arrays["log_likelihood"][positive]+arrays["log_prior"][positive]-arrays["log_q"][positive]
        residuals["log_psi_identity"] = float(np.max(abs(identity-arrays["log_psi"][positive])))
        residuals["normalized_weights"] = float(np.max(abs(w-np.exp(arrays["log_weights"]-result.logz))))
        history = result.de_settings["recovery"]["attempts"]
        passed = all(value < 1e-6 for value in residuals.values()) and abs(w.sum()-1) < 1e-10
        report = {"event": event, "numerical_audit_passed": bool(passed),
            "maximum_absolute_residuals": residuals, "weight_sum": float(w.sum()),
            "maximum_weight": float(w.max()), "top10_mass": float(np.sort(w)[-10:].sum()),
            "weight_ess": float(1/np.sum(w*w)), "positive_points": len(theta),
            "unique_positive_points": len(np.unique(theta, axis=0)),
            "recovery_retries": sum(row["attempt"] > 1 for row in history),
            "failed_attempts": sum(not row["succeeded"] for row in history),
            "n_iterations": result.niter, "likelihood_replay_calls": len(theta),
            "input_sha256": {str(p): digest(p) for p in (receipt_path, out/"invocation.json", out/"nis/result.npz")},
            "limitations": "Bookkeeping and pointwise replay only; does not certify proposal sampling, mixing, missing modes or unbiased volumes."}
        reports.append(report)
        print(json.dumps(report), flush=True)
    write_new(args.output, {"script_sha256": digest(__file__), "events": reports})
    if not all(report["numerical_audit_passed"] for report in reports):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
