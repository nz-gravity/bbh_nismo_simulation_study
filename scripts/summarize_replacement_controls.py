#!/usr/bin/env python3
"""Compare immutable pilot/control outputs using the webpage's marginal JSD."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

from build_main_results import MainResults, js_divergence, marginal_mass
from local_morphnis import PARAMETERS, digest, read_event, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--cheap", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--control", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    main_results = MainResults(args.cheap, args.reference, args.campaign)
    entries = []
    for event in (23, 47):
        receipt = json.loads((args.campaign/"outcomes"/f"event_{event:03d}.json").read_text())
        entries.append(("original", Path(receipt["output"])))
    entries.extend((p.name, p) for p in args.control)
    rows, curves = [], {23: [], 47: []}
    for label, path in entries:
        inv = json.loads((path/"invocation.json").read_text())["arguments"]
        event = inv["event"]
        baseline, reference, ref_mass = main_results.baseline(event)
        pilot, _, _ = read_event(args.cheap, event, "cheap")
        validation = json.loads((path/"validation.json").read_text()) if (path/"validation.json").exists() else {}
        row = {"event": event, "run": label, "output": str(path),
               "lnz_reference": baseline["lnz_reference"],
               "delta_lnz_cheap_reference": baseline["delta_lnz_cheap_reference"],
               "jsd_cheap_reference_bits": baseline["jsd_cheap_reference_bits"],
               "sampling_seed": inv["seed"], "fit_seed": inv["fit_seed"],
               "pilot_likelihood_calls": pilot["likelihood_evaluations"],
               "validation_likelihood_calls_additional": validation.get("likelihood_calls")}
        if (path/"failure.json").exists():
            failure = json.loads((path/"failure.json").read_text())
            row.update(status="failed", error=failure["error"],
                       likelihood_calls=failure.get("likelihood_calls"),
                       invocation_seconds=failure["seconds"],
                       failed_iteration=(failure.get("recovery_history") or [{}])[-1].get("iteration"))
            if row["likelihood_calls"] is not None:
                row["pilot_inclusive_likelihood_calls"] = row["likelihood_calls"]+pilot["likelihood_evaluations"]
            rows.append(row)
            continue
        if not (path/"comparison.json").exists():
            row["status"] = "pending"
            rows.append(row)
            continue
        comparison = json.loads((path/"comparison.json").read_text())
        if comparison["status"] != "converged":
            row.update(status="non_converged", termination_reason=comparison["termination_reason"],
                       likelihood_calls=comparison["nis"]["likelihood_calls"])
            rows.append(row)
            continue
        with np.load(path/"nis/result.npz", allow_pickle=False) as saved:
            samples = np.concatenate((saved["dead_theta"], saved["final_live_theta"]))
            weights = np.exp(saved["log_posterior_weights"])
        if not np.isclose(weights.sum(), 1, rtol=0, atol=1e-10):
            raise ValueError("Weights not normalized")
        marginal = {name: marginal_mass(samples[:, j], baseline["marginal_estimator"][name], weights)
                    for j, name in enumerate(PARAMETERS)}
        jsd = {name: js_divergence(marginal[name], ref_mass[name]) for name in PARAMETERS}
        row.update(status="stopping_threshold_reached" if comparison["status"] == "converged" else comparison["status"],
                   delta_lnz_nismo_reference=comparison["delta_logz_nis_reference"],
                   delta_lnz_statistical_error=comparison["delta_logz_nis_reference_statistical_error"],
                   jsd_nismo_reference_bits=float(np.mean(list(jsd.values()))),
                   jsd_marginals_bits=jsd, weight_ess=comparison["nis"]["weight_ess"],
                   likelihood_calls=comparison["nis"]["likelihood_calls"],
                   pilot_inclusive_likelihood_calls=comparison["cost_including_pilot"]["likelihood_calls"],
                   sampler_seconds=comparison["nis"]["sampler_seconds"],
                   retries=comparison["nis"]["retry_attempts"],
                   result_sha256=digest(path/"nis/result.npz"))
        curves[event].append((label, marginal))
        rows.append(row)
    write_new(args.output/"comparison.json", {"metric": "Mean of eight marginal JSDs in bits; not joint JSD",
        "limitations": "Numerical stopping and Kish ESS do not validate mixing. Statistical errors exclude sampler/proposal bias. Reference is thinned to 1000 draws. All controls retained, no best-seed selection.",
        "script_sha256": digest(__file__), "runs": rows})
    columns = ["event", "run", "status", "lnz_reference", "delta_lnz_cheap_reference", "delta_lnz_nismo_reference",
               "delta_lnz_statistical_error", "jsd_cheap_reference_bits", "jsd_nismo_reference_bits",
               "weight_ess", "retries", "likelihood_calls", "pilot_inclusive_likelihood_calls",
               "validation_likelihood_calls_additional", "sampler_seconds", "invocation_seconds", "failed_iteration", "error"]
    with (args.output/"comparison.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for event in (23, 47):
        baseline, _, ref_mass = main_results.baseline(event)
        _, cheap, _ = read_event(args.cheap, event, "cheap")
        fig, axes = plt.subplots(2, 4, figsize=(15, 6), constrained_layout=True)
        for ax, name in zip(axes.flat, PARAMETERS):
            spec = baseline["marginal_estimator"][name]
            edges = np.linspace(spec["low"], spec["high"], spec["grid_bins"]+1)
            x, dx = (edges[:-1]+edges[1:])/2, edges[1]-edges[0]
            ax.plot(x, ref_mass[name]/dx, color="black", label="Dynesty 2000")
            ax.plot(x, marginal_mass(cheap[name], spec)/dx, color="0.6", label="Cheap Dynesty", linestyle="--")
            for label, marginal in curves[event]:
                ax.plot(x, marginal[name]/dx, label=label, alpha=.85)
            ax.set(xlabel=name, ylabel="Density")
        handles, labels = axes.flat[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="outside upper center", ncol=3, fontsize=9,
                   title=f"Event {event}: weighted marginals, shared reference bandwidth")
        fig.savefig(args.output/f"event_{event:03d}_marginals.png", dpi=180, bbox_inches="tight")
        plt.close(fig)
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
