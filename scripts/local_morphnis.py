#!/usr/bin/env python3
"""Run a guarded local NIS comparison using original or audited reconstructed data.

The compact release supplies complete cheap training rows and a thinned,
independent reference for preliminary comparison. It supplies no strain arrays.
Original data require exact checksums. Reconstructed data require an explicit
--reconstruction-audit receipt and fresh likelihood/prior replays. This script
never generates data or submits scheduler jobs.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import time
import traceback
import zipfile
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd

PARAMETERS = ("chirp_mass", "mass_ratio", "a_1", "a_2", "tilt_1", "tilt_2", "phi_12", "phi_jl")
LABELS = (r"$\mathcal{M}\ [M_\odot]$", r"$q$", r"$a_1$", r"$a_2$",
          r"$\theta_1\ [\mathrm{rad}]$", r"$\theta_2\ [\mathrm{rad}]$",
          r"$\phi_{12}\ [\mathrm{rad}]$", r"$\phi_{JL}\ [\mathrm{rad}]$")
TOLERANCE = 1e-6


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_new(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def revision(directory):
    return subprocess.check_output(["git", "-C", str(directory), "rev-parse", "HEAD"], text=True).strip()


def resolve_demo_settings(repo, event, output, morph_phase=False):
    """Read executable demo defaults; retain our existing audited pilot/target.

    Only the post-processing stage is reused. The demo's new random-walk pilot
    is not run, and the reference never enters proposal fitting.
    """
    path = Path(repo) / "examples/lvk/rwalk_morph_demo.py"
    demo = load_helpers(path)
    defaults = demo.parse_args([str(event), "--output-dir", str(output)])
    return {"demo": str(path), "demo_sha256": digest(path),
            "bandwidth_scale": defaults.bandwidth_scale, "bw": defaults.bw,
            "move_weights": dict(demo.LOCAL_MOVE_WEIGHTS), "move_adapt": False,
            "de_adapt": True, "stretch_scale": 1.5,
            "morph_phase": morph_phase, "morph_batch_size": defaults.morph_batch_size,
            "training_source": "existing complete cheap nlive=100 posterior; no new pilot"}


def read_event(archive, event, kind):
    expected = json.loads((Path(__file__).parents[1] / "results_manifest.json").read_text())
    package = next(p for p in expected["result_packages"] if p["kind"] == kind)
    if digest(archive) != package["sha256"]:
        raise ValueError(f"{kind} release checksum mismatch")
    with zipfile.ZipFile(archive) as source:
        prefix = source.namelist()[0].split("/")[0]
        root = f"{prefix}/events/injection_{event:03d}/"
        summary = json.loads(source.read(root + "summary.json"))
        data = source.read(root + "posterior.csv")
        if hashlib.sha256(data).hexdigest() != summary["posterior_sha256"]:
            raise ValueError("Posterior checksum mismatch")
        posterior = pd.read_csv(io.BytesIO(data), float_precision="round_trip")
        if len(posterior) != summary["posterior_rows"] or summary["event_id"] != event:
            raise ValueError("Event identity/row count mismatch")
        if not np.isfinite(posterior.to_numpy()).all():
            raise ValueError("Nonfinite posterior")
        manifest = json.loads(source.read(root + "strain_manifest.json")) if kind == "cheap" else None
    return summary, posterior, manifest


def load_helpers(path):
    spec = importlib.util.spec_from_file_location("morphnis_lvk_helpers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_data_origin(data_path, original, event, training_rows, receipt_path=None):
    """Bind a target to original bytes or an explicitly audited reconstruction."""
    actual = json.loads(data_path.with_suffix(".json").read_text())
    data_hash = digest(data_path)
    if receipt_path is None:
        if data_hash != original["data_sha256"]:
            raise ValueError("Frozen data do not match original event checksum; supply a validated reconstruction receipt")
        if actual != original:
            raise ValueError("Frozen strain manifest mismatch")
        return actual, {"kind": "original_frozen", "data_sha256": data_hash,
                        "original_data_sha256": original["data_sha256"]}
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("event") != event or receipt.get("numerical_contract_passed") is not True:
        raise ValueError("Wrong or unsuccessful reconstruction receipt")
    if (data_hash != actual.get("data_sha256") or data_hash != receipt.get("actual_data_sha256")
            or original["data_sha256"] != receipt.get("expected_data_sha256")):
        raise ValueError("Reconstruction receipt/data checksum mismatch")
    for key in ("scientific_config", "core_versions", "geometry"):
        if actual[key] != original[key]:
            raise ValueError(f"Reconstructed target changed {key}")
    for key, required_points in (("posterior_audit", training_rows), ("reference_holdout_audit", 32)):
        check = receipt.get(key, {})
        if check.get("n_points", 0) < required_points:
            raise ValueError(f"Incomplete reconstruction replay: {key}")
        for metric in ("max_abs_log_prior_difference", "max_abs_log_likelihood_residual",
                       "offset_to_documented_convention_residual"):
            value = check.get(metric, np.inf)
            if not np.isfinite(value) or not 0 <= value <= TOLERANCE:
                raise ValueError(f"Reconstruction replay failed: {key}/{metric}")
    if not np.isfinite(receipt.get("noise_difference", np.inf)) or abs(receipt["noise_difference"]) > TOLERANCE:
        raise ValueError("Reconstruction noise likelihood mismatch")
    return actual, {"kind": "validated_reconstruction", "data_sha256": data_hash,
        "original_data_sha256": original["data_sha256"], "receipt_sha256": digest(receipt_path),
        "original_likelihood_id": original["likelihood_id"],
        "reconstructed_likelihood_id": actual["likelihood_id"]}


def audit(model, posterior, helper, noise, n_points=32):
    result = helper.audit_posterior_contract(
        model=model, result=SimpleNamespace(posterior=posterior),
        samples=posterior[list(PARAMETERS)].to_numpy(), n_points=n_points,
    )
    # Full likelihood or ratio-to-noise are the only documented conventions.
    result["offset_to_documented_convention_residual"] = min(
        abs(result["log_likelihood_offset"]), abs(result["log_likelihood_offset"] - noise)
    )
    if max(result["max_abs_log_prior_difference"],
           result["max_abs_log_likelihood_residual"],
           result["offset_to_documented_convention_residual"]) > TOLERANCE:
        raise ValueError(f"Scientific likelihood/prior replay mismatch: {result}")
    return result


def compare_posteriors(samples, weights, cheap, reference):
    from scipy.stats import wasserstein_distance

    metrics = {}
    for j, name in enumerate(PARAMETERS):
        values = samples[:, j]
        a, b = cheap[name].to_numpy(), reference[name].to_numpy()
        origin = None
        if name.startswith("phi_"):
            # A common seam for descriptive distances; this is not a circular
            # optimal-transport metric or a significance test.
            origin = float(np.angle(np.mean(np.exp(1j * b))))
            values, a, b = [(x - origin + np.pi) % (2 * np.pi) - np.pi for x in (values, a, b)]
        metrics[name] = {
            "nis_reference_wasserstein": float(wasserstein_distance(values, b, u_weights=weights)),
            "cheap_reference_wasserstein": float(wasserstein_distance(a, b)),
            "angular_center_radians": origin,
        }
    return metrics


def plot_corner(output, result, cheap, reference, manifest, event):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    import corner

    positive = result.posterior_weights > 0
    data = result.samples[positive]
    weights = result.posterior_weights[positive]
    truth = [manifest["scientific_config"]["settings"]["injection"][k] for k in PARAMETERS]
    bounds = [(14, 20), (.125, 1), (0, .99), (0, .99), (0, np.pi), (0, np.pi), (0, 2*np.pi), (0, 2*np.pi)]
    all_data = np.concatenate((data, cheap[list(PARAMETERS)], reference[list(PARAMETERS)], [truth]))
    ranges = []
    for j, (low, high) in enumerate(bounds):
        left, right = np.min(all_data[:, j]), np.max(all_data[:, j])
        pad = max(.025 * (right-left), 1e-8)
        ranges.append((low, high) if j >= 6 else (max(low, left-pad), min(high, right+pad)))
    fig = plt.figure(figsize=(14, 14))
    common = dict(fig=fig, labels=list(LABELS), range=ranges, bins=30,
                  smooth=1, smooth1d=1, plot_datapoints=False, plot_density=False,
                  fill_contours=False, levels=(.5, .9), max_n_ticks=3)
    corner.corner(reference[list(PARAMETERS)].to_numpy(), color="#d97916", truths=truth,
                  truth_color="#777777", hist_kwargs={"linestyle": "--"},
                  contour_kwargs={"linestyles": "--"}, **common)
    corner.corner(cheap[list(PARAMETERS)].to_numpy(), color="#2166ac",
                  **common)
    corner.corner(data, weights=weights, color="#28814c",
                  hist_kwargs={"linestyle": ":"}, contour_kwargs={"linestyles": ":"}, **common)
    # Corner's smoothed 1D path calls plot(), not hist(). Normalize each
    # marginal separately rather than passing histogram keywords to plot().
    from scipy.ndimage import gaussian_filter1d
    axes = np.asarray(fig.axes).reshape(8, 8)
    integrals = []
    for j, name in enumerate(PARAMETERS):
        ax = axes[j, j]
        ax.clear()
        edges = np.linspace(*ranges[j], 31)
        centers = (edges[:-1]+edges[1:])/2
        areas, peaks = [], []
        for series, series_weights, color, style in (
            (reference[name].to_numpy(), None, "#d97916", "--"),
            (cheap[name].to_numpy(), None, "#2166ac", "-"),
            (data[:, j], weights, "#28814c", ":")):
            density, _ = np.histogram(series, bins=edges, weights=series_weights, density=True)
            density = gaussian_filter1d(density, 1.)
            area = float(np.sum(density*np.diff(edges)))
            if not np.isclose(area, 1., atol=1e-10):
                raise ValueError("Marginal histogram normalization failed")
            areas.append(area)
            peaks.append(float(density.max()))
            ax.plot(centers, density, color=color, linestyle=style, linewidth=1.5)
        ax.axvline(truth[j], color="#777777", linewidth=.8)
        ax.set_xlim(ranges[j])
        ax.set_ylim(0, max(peaks)*1.08)
        ax.set_yticks([])
        ax.tick_params(labelbottom=j == 7)
        if j == 7:
            ax.set_xlabel(LABELS[j])
        integrals.append(areas)
    fig.subplots_adjust(top=.92)
    fig.suptitle(f"Injection {event:03d} · local NIS comparison", fontsize=16)
    handles = [Line2D([], [], color=c, linestyle=ls, label=label) for c, ls, label in (
        ("#2166ac", "-", f"Cheap: {len(cheap)} draws"),
        ("#d97916", "--", f"Reference: {len(reference)} retained draws"),
        ("#28814c", ":", "NIS: weighted draws"))]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, .965), ncol=3, frameon=False)
    fig.savefig(output / "corner.png", dpi=120, facecolor="white")
    plt.close(fig)
    return {"diagonal_integrals_reference_cheap_nis": integrals,
            "ranges": ranges, "contour_levels": [.5, .9]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event", type=int)
    for name in ("cheap", "reference", "benchmark-repo", "nismo-repo", "data", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--nlive", type=int, default=100)
    parser.add_argument("--fit-seed", type=int, default=20261104)
    parser.add_argument("--seed", type=int, default=20262104)
    parser.add_argument("--dlogz", type=float, default=.1)
    parser.add_argument("--max-iterations", type=int, default=10000)
    parser.add_argument("--de-retries", type=int, default=0)
    parser.add_argument("--allow-heuristic-recovery", action="store_true",
                        help="Explicitly permit potentially biased successful-retry selection")
    parser.add_argument("--fixed-walks", action="store_true", help="Disable between-walk DE adaptation")
    parser.add_argument("--walk-n-steps", type=int)
    parser.add_argument("--demo-settings", action="store_true",
                        help="Use the checked-out rwalk_morph_demo post-processing configuration")
    parser.add_argument("--morph-phase", action="store_true",
                        help="Enable the demo's independent cached proposal pool")
    parser.add_argument("--demo-bw", type=float,
                        help="Use the demo's documented fixed --bw option")
    parser.add_argument("--demo-pool-size", type=int,
                        help="Explicit override for the demo's proposal-pool size")
    parser.add_argument("--demo-moves", choices=("de-stretch", "de-rwalk"), default="de-stretch",
                        help="Fixed 80/20 move mixture for the demo post-processing stage")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--reconstruction-audit", type=Path)
    args = parser.parse_args()
    if args.de_retries and not args.allow_heuristic_recovery:
        parser.error("Retries condition on successful movement; use --allow-heuristic-recovery to opt in explicitly")
    if args.morph_phase and not args.demo_settings:
        parser.error("--morph-phase requires --demo-settings")
    if (args.demo_bw is not None or args.demo_pool_size is not None) and not args.demo_settings:
        parser.error("Demo overrides require --demo-settings")
    if args.demo_bw is not None and (not np.isfinite(args.demo_bw) or args.demo_bw <= 0):
        parser.error("--demo-bw must be finite and positive")
    if args.demo_pool_size is not None and args.demo_pool_size < args.nlive:
        parser.error("Demo pool must include at least nlive proposals")
    if args.demo_settings and args.fixed_walks:
        parser.error("The demo uses adaptation; omit --fixed-walks")
    if args.nlive < 4 or args.max_iterations < 1 or not np.isfinite(args.dlogz) or args.dlogz <= 0:
        parser.error("Invalid sampling settings")
    if not (0 <= args.fit_seed < 2**32 and 0 <= args.seed < 2**32) or args.de_retries < 0:
        parser.error("Invalid seeds or retries")
    # mkdir is the exclusive reservation. A failed/partial run also occupies
    # its directory; reruns must choose a fresh name, never silently resume.
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    write_new(args.output / "invocation.json", {
        "created_utc": datetime.now(timezone.utc).isoformat(), "pid": os.getpid(),
        "arguments": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "training_policy": "cheap only; every saved row; thin=1; no sample cap",
        "reference_policy": "holdout for contract validation and post-run comparison; no training/tuning",
        "morphnis_commit": revision(args.nismo_repo), "benchmark_commit": revision(args.benchmark_repo),
        "morphnis_source_sha256": {str(p.relative_to(args.nismo_repo)): digest(p)
            for p in sorted((args.nismo_repo / "src/morphnis").glob("*.py"))},
        "script_sha256": digest(__file__),
        "versions": {k: version(k) for k in ("morphnis", "morphZ", "bilby", "lalsuite", "numpy", "scipy", "pandas")},
    })
    sampler = None
    phase = "validation"
    try:
        cheap, training, manifest = read_event(args.cheap, args.event, "cheap")
        ref, reference, _ = read_event(args.reference, args.event, "reference")
        if cheap["config"]["kwargs"]["nlive"] != 100 or ref["sampler_kwargs"]["nlive"] != 2000:
            raise ValueError("Wrong Dynesty baseline")
        if cheap["original_posterior_rows"] != len(training):
            raise ValueError("Cheap archive is not complete training data")
        if ref["comparison_audit"]["comparison_likelihood_id"] != cheap["likelihood_id"]:
            raise ValueError("Reference/cheap event matching failed")
        if tuple(ref["search_parameter_keys"]) != PARAMETERS:
            raise ValueError("Parameterization mismatch")
        target_manifest, data_origin = validate_data_origin(
            args.data, manifest, args.event, len(training), args.reconstruction_audit)
        sys.path.insert(0, str(args.benchmark_repo.resolve()))
        # --nismo-repo must select the implementation, including an isolated
        # patched worktree; an unrelated editable install must not win.
        sys.path.insert(0, str(args.nismo_repo.resolve() / "src"))
        import morphnis
        if not Path(morphnis.__file__).resolve().is_relative_to(args.nismo_repo.resolve() / "src"):
            raise RuntimeError("Loaded morphnis does not match --nismo-repo; use a fresh Python process")
        from benchmark import injection
        helper = load_helpers(args.nismo_repo / "examples/lvk/morphnis_computation.py")
        with patch.object(injection, "settings", return_value=manifest["scientific_config"]["settings"]):
            likelihood, priors = injection.build_likelihood(args.data)
        model = helper.build_model(likelihood=likelihood, priors=priors, names=PARAMETERS,
                                   fixed_values=helper.fixed_parameter_values(priors))
        noise = float(likelihood.noise_log_likelihood())
        if max(abs(cheap["log_noise_evidence"]-noise), abs(ref["log_noise_evidence"]-noise)) > TOLERANCE:
            raise ValueError("Noise-evidence mismatch")
        audits = {"cheap": audit(model, training, helper, noise,
                                 n_points=len(training) if args.reconstruction_audit else 32),
                  "reference_holdout": audit(model, reference, helper, noise)}
        audits["likelihood_calls"] = sum(x["n_points"] for x in audits.values())
        audits["seconds"] = time.perf_counter()-started
        audits["data_sha256"] = digest(args.data)
        audits["data_origin"] = data_origin
        write_new(args.output / "validation.json", audits)
        if args.audit_only:
            return
        from morphnis import MorphImportance, NestedImportanceSampler
        settings = (resolve_demo_settings(args.nismo_repo, args.event, args.output, args.morph_phase)
                    if args.demo_settings else {
                        "bandwidth_scale": 1., "bw": None,
                        "move_weights": {"de": .8, "stretch": .2},
                        "move_adapt": False, "de_adapt": not args.fixed_walks,
                        "stretch_scale": 1.5, "morph_phase": False, "morph_batch_size": 1000})
        if args.demo_bw is not None:
            settings.update(bandwidth_scale=1., bw=args.demo_bw)
        if args.demo_pool_size is not None:
            settings["morph_batch_size"] = args.demo_pool_size
        if args.demo_moves == "de-rwalk":
            settings["move_weights"] = {"de": .8, "stretch": 0., "rwalk": .2}
        write_new(args.output / "workflow_settings.json", settings | {
            "nlive": args.nlive, "seed": args.seed, "fit_seed": args.fit_seed,
            "dlogz": args.dlogz, "max_iterations": args.max_iterations,
            "de_retries": args.de_retries, "thin": 1,
            "reference_policy": "independent holdout; excluded from training and tuning"})
        phase = "fit"
        fit_started = time.perf_counter()
        proposal = MorphImportance.fit(training[list(PARAMETERS)].to_numpy(),
                                       parameter_names=PARAMETERS, seed=args.fit_seed, thin=1,
                                       bandwidth_scale=settings["bandwidth_scale"], bw=settings["bw"])
        fit_seconds = time.perf_counter()-fit_started
        write_new(args.output / "proposal.json", proposal.metadata)
        sampler = NestedImportanceSampler(model=model, importance=proposal, nlive=args.nlive,
            seed=args.seed, **{k: settings[k] for k in (
                "move_weights", "move_adapt", "de_adapt", "stretch_scale", "morph_phase", "morph_batch_size")},
            de_retries=args.de_retries, walk_n_steps=args.walk_n_steps)
        phase = "sampling"
        result = sampler.run(dlogz=args.dlogz, max_iterations=args.max_iterations, print_progress=True)
        phase = "export"
        result.save(args.output / "nis")
        weights = result.posterior_weights
        history = result.de_settings["recovery"]["attempts"]
        retry_rows = [row for row in history if row["attempt"] > 1]
        converged = result.termination_reason in ("dlogz", "flat_log_psi")
        error = float(np.hypot(result.logzerr, ref["log_evidence_err"]))
        payload = {
            "event": args.event, "scope": "local NIS; thinned reference posterior; full-inference baseline evidence/cost",
            "status": "converged" if converged else "non_converged", "termination_reason": result.termination_reason,
            "likelihood_id": target_manifest["likelihood_id"], "baseline_likelihood_id": manifest["likelihood_id"],
            "data_origin": data_origin, "training": proposal.metadata, "workflow_settings": settings,
            "nis": {"log_evidence": result.logz, "log_evidence_err": result.logzerr,
                "n_iterations": result.niter, "nlive": result.nlive,
                "weight_ess": float(1 / np.sum(weights**2)), "weight_ess_accounts_for_correlations": False,
                "likelihood_calls": result.n_likelihood_calls, "sampler_seconds": result.runtime_seconds,
                "fit_seconds": fit_seconds, "morph_phase": result.move_settings.get("morph_phase"),
                "recovery_iterations": len({row["iteration"] for row in retry_rows}),
                "retry_attempts": len(retry_rows), "failed_walk_attempts": sum(not row["succeeded"] for row in history)},
            "cheap": cheap, "reference": ref,
            "delta_logz_nis_reference": result.logz-ref["log_evidence"],
            "delta_logz_nis_reference_statistical_error": error,
            "delta_logz_cheap_reference": cheap["log_evidence"]-ref["log_evidence"],
            "nis_minus_cheap": result.logz-cheap["log_evidence"],
            "posterior_distances": compare_posteriors(result.samples, weights, training, reference),
            "cost_including_pilot": {
                "likelihood_calls": cheap["likelihood_evaluations"]+result.n_likelihood_calls,
                "validation_likelihood_calls_additional": audits["likelihood_calls"],
                "pilot_reported_sampling_seconds": cheap["sampling_seconds"],
                "pilot_reported_invocation_seconds": cheap.get("invocation_seconds"),
                "nis_fit_and_sampling_seconds": fit_seconds+result.runtime_seconds,
                "wall_times_from_different_hardware_are_not_speedup_estimates": True},
            "limitations": ["Weight ESS does not measure chain autocorrelation or missing modes.",
                "Reported evidence errors are statistical approximations, not bounds on proposal or recovery bias.",
                "Retry selection is heuristic; inspect recovery counts and repeat with fail-fast/stricter walks.",
                "Reference is independently sampled but is not exact truth; 1000 retained posterior draws limit comparisons.",
                "Original full reference histories and scheduler completion remain uninspected."],
        }
        write_new(args.output / "comparison.json", payload)
        try:
            plot_checks = plot_corner(args.output, result, training, reference, manifest, args.event)
            write_new(args.output / "plot_validation.json", plot_checks)
        except Exception as error:
            # A renderer failure must not relabel a completed sampler outcome.
            write_new(args.output / "plot_failure.json", {"error": str(error),
                      "traceback": traceback.format_exc(), "sampler_status": payload["status"]})
        print(json.dumps({"status": payload["status"], "delta_logz_nis_reference": payload["delta_logz_nis_reference"],
                          **payload["nis"]}), flush=True)
        if not converged:
            raise SystemExit(3)
    except Exception as error:
        failure = {"status": "failed", "phase": phase, "error_type": type(error).__name__, "error": str(error),
                   "traceback": traceback.format_exc(), "seconds": time.perf_counter()-started}
        if sampler is not None:
            failure["likelihood_calls"] = sampler.evaluate.n_likelihood_calls
            failure["prior_calls"] = sampler.evaluate.n_prior_calls
            failure["morph_phase"] = sampler._morph_metadata()
            failure["recovery_history"] = sampler._de_recovery_history
        write_new(args.output / "failure.json", failure)
        raise


if __name__ == "__main__":
    main()
