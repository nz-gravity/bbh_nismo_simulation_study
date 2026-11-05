#!/usr/bin/env python3
"""Replay a pilot with independent rejection or long, fixed, fail-fast walks.

Use a fresh output directory. Training/fit seed match the recorded pilot;
reference data remain holdout. Limits stop the control, never manufacture a
successful endpoint. This is a diagnostic, not a replacement campaign runner.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event", type=int, choices=(23, 47))
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--nismo-repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("rejection", "fixed-walk"), required=True)
    parser.add_argument("--seed", type=int, default=20261106)
    parser.add_argument("--walk-steps", type=int, default=1000)
    parser.add_argument("--proposal-budget", type=int, default=1000000)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a fresh directory")
    if args.proposal_budget < 1 or args.walk_steps < 1:
        parser.error("Budgets must be positive")
    sys.path.insert(0, str(args.nismo_repo.resolve()/"src"))
    import morphnis
    from morphnis.constrained import draw_constrained_rejection
    from morphnis.diagnostics import Replacement
    from local_morphnis import digest, main as run_local
    control_hash = digest(__file__)
    runner_hash = digest(Path(__file__).with_name("local_morphnis.py"))
    source_hashes = {str(p.relative_to(args.nismo_repo)): digest(p)
                    for p in sorted((args.nismo_repo/"src/morphnis").glob("*.py"))}

    original = morphnis.NestedImportanceSampler

    class Control(original):
        def _draw_replacement(self, live, worst, iteration):
            remaining = args.proposal_budget-self.evaluate.n_prior_calls
            if remaining < 1:
                raise RuntimeError("Diagnostic proposal budget exhausted")
            if args.mode == "fixed-walk":
                return super()._draw_replacement(live, worst, iteration)
            discarded = live[worst]
            prior_before = self.evaluate.n_prior_calls
            rejected_before = self.evaluate.n_prior_rejected
            likelihood_before = self.evaluate.n_likelihood_calls
            point = draw_constrained_rejection(
                threshold=discarded.log_psi, evaluate=self.evaluate, rng=self.rng,
                max_proposals=min(remaining, 500000))
            return Replacement(
                point=point, start_index=-1, start_theta=discarded.theta,
                n_proposed=self.evaluate.n_prior_calls-prior_before,
                n_prior_rejected=self.evaluate.n_prior_rejected-rejected_before,
                n_constraint_passed=1, n_mh_accepted=0,
                squared_displacement=float(np.sum((point.theta-discarded.theta)**2)),
                standardized_squared_displacement=0.,
                likelihood_calls=self.evaluate.n_likelihood_calls-likelihood_before)

    receipt = json.loads((args.campaign/"outcomes"/f"event_{args.event:03d}.json").read_text())
    invocation = Path(receipt["output"])/"invocation.json"
    recorded = json.loads(invocation.read_text())["arguments"]
    argv = [str(__file__), str(args.event)]
    for name in ("cheap", "reference", "benchmark_repo", "data", "fit_seed", "reconstruction_audit"):
        argv += ["--"+name.replace("_", "-"), str(recorded[name])]
    argv += ["--nismo-repo", str(args.nismo_repo), "--output", str(args.output),
             "--seed", str(args.seed), "--nlive", "100", "--dlogz", "0.1",
             "--de-retries", "0", "--fixed-walks", "--max-iterations", "10000"]
    if args.mode == "fixed-walk":
        argv += ["--walk-n-steps", str(args.walk_steps)]
    morphnis.NestedImportanceSampler = Control
    sys.argv = argv
    try:
        run_local()
    finally:
        if args.output.exists():
            (args.output/"control.json").write_text(json.dumps({
                "mode": args.mode, "proposal_budget": args.proposal_budget,
                "walk_steps": args.walk_steps if args.mode == "fixed-walk" else None,
                "sampling_seed": args.seed, "source_invocation": str(invocation),
                "source_invocation_sha256": digest(invocation),
                "control_script_sha256": control_hash,
                "local_runner_sha256": runner_hash,
                "nismo_source_sha256": source_hashes,
                "settings_policy": "Preset diagnostic controls; reference excluded from training and tuning",
                "independent_replacements": args.mode == "rejection",
            }, indent=2)+"\n")


if __name__ == "__main__":
    main()
