#!/usr/bin/env python3
"""Export the study's five main results without evaluating a likelihood.

Reference lnZ, cheap/reference and NIS/reference lnZ differences, and the two
posterior Jensen-Shannon divergences. JSD is the mean of eight 1D marginal
divergences in bits, not an 8D joint divergence or the square-root JS distance.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import io
import json
import math
import os
import shutil
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.special import rel_entr

from local_morphnis import PARAMETERS, digest, read_event

SCHEMA = 1
METHOD = "shared-reference-scott-smoothed-histogram-v1"


def js_divergence(p, q):
    """Jensen-Shannon divergence in bits; independent of sample normalization."""
    p, q = np.asarray(p, float), np.asarray(q, float)
    if p.shape != q.shape or p.ndim != 1 or not np.isfinite([p, q]).all():
        raise ValueError("JSD needs matching finite probability vectors")
    if np.any(p < 0) or np.any(q < 0) or p.sum() <= 0 or q.sum() <= 0:
        raise ValueError("JSD probabilities must be nonnegative with positive mass")
    p, q = p/p.sum(), q/q.sum()
    mixture = (p+q)/2
    value = float((rel_entr(p, mixture).sum()+rel_entr(q, mixture).sum())/(2*np.log(2)))
    if not -1e-12 <= value <= 1+1e-12:
        raise ValueError("JSD is outside [0,1] bits")
    return float(np.clip(value, 0, 1))


def marginal_spec(reference, low, high, periodic=False, min_grid=512, max_grid=8192):
    reference = np.asarray(reference, float)
    if len(reference) < 3 or not np.isfinite(reference).all() or high <= low:
        raise ValueError("Invalid reference marginal")
    centered = reference
    if periodic:
        phase = (reference-low)*2*np.pi/(high-low)
        center = np.angle(np.exp(1j*phase).mean())
        centered = np.angle(np.exp(1j*(phase-center)))*(high-low)/(2*np.pi)
    scale = float(np.std(centered, ddof=1))
    if scale <= 0:
        raise ValueError("Degenerate sampled reference marginal")
    raw_bandwidth = scale*len(reference)**(-1/5)
    floor = 4*(high-low)/max_grid
    bandwidth = max(raw_bandwidth, floor)
    grid = min(max_grid, max(min_grid, math.ceil(4*(high-low)/bandwidth)))
    return {"low": float(low), "high": float(high), "periodic": periodic,
            "bandwidth": bandwidth, "bandwidth_floor_applied": raw_bandwidth < floor,
            "grid_bins": int(grid), "sigma_bins": bandwidth*grid/(high-low)}


def marginal_mass(samples, spec, weights=None):
    x = np.asarray(samples, float)
    w = np.ones(len(x), float) if weights is None else np.asarray(weights, float)
    if x.ndim != 1 or w.shape != x.shape or not np.isfinite(x).all() or not np.isfinite(w).all():
        raise ValueError("Invalid marginal samples/weights")
    if np.any(w < 0) or w.sum() <= 0:
        raise ValueError("Invalid posterior weights")
    positive = w > 0
    x, w = x[positive], w[positive]
    low, high = spec["low"], spec["high"]
    if spec["periodic"]:
        x = (x-low) % (high-low)+low
    else:
        if np.any(x < low-1e-12*(high-low)) or np.any(x > high+1e-12*(high-low)):
            raise ValueError("Positive posterior mass outside prior support")
        x = np.clip(x, low, high)
    counts, _ = np.histogram(x, bins=spec["grid_bins"], range=(low, high), weights=w/w.sum())
    mass = gaussian_filter1d(counts, spec["sigma_bins"],
                             mode="wrap" if spec["periodic"] else "reflect", truncate=4.)
    if not np.isclose(mass.sum(), 1., rtol=0, atol=1e-10):
        raise ValueError("Marginal density mass is not normalized")
    return mass/mass.sum()


def load_nis(result_path, comparison, expected_hash):
    if digest(result_path) != expected_hash:
        raise ValueError("NIS NPZ differs from its authoritative campaign receipt")
    with np.load(result_path, allow_pickle=False) as z:
        metadata = json.loads(str(z["metadata_json"]))
        if tuple(metadata["parameter_names"]) != PARAMETERS:
            raise ValueError("NIS coordinate order mismatch")
        samples = np.concatenate((z["dead_theta"], z["final_live_theta"]))
        weights = np.exp(z["log_posterior_weights"])
    if not np.isclose(weights.sum(), 1., rtol=0, atol=1e-10) or not np.isfinite(samples).all():
        raise ValueError("Invalid cached NIS posterior")
    if abs(metadata["logz"]-comparison["nis"]["log_evidence"]) > 1e-9:
        raise ValueError("NIS evidence disagrees with cached NPZ")
    return samples, weights/weights.sum()


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+f".{os.getpid()}.tmp")
    temporary.write_text(value if isinstance(value, str) else json.dumps(value, indent=2, allow_nan=False)+"\n")
    temporary.replace(path)


def read_receipt(path):
    # Controller receipts are exclusive new files; allow a just-created file's
    # short write to finish, but never silently replace malformed evidence.
    for attempt in range(3):
        try:
            return json.loads(Path(path).read_text())
        except json.JSONDecodeError:
            if attempt == 2:
                raise
            time.sleep(.1)


class MainResults:
    def __init__(self, cheap, reference, campaign, null_repeats=32):
        self.cheap, self.reference, self.campaign = Path(cheap), Path(reference), Path(campaign)
        self.null_repeats = null_repeats
        self.baselines, self.cache = {}, {}

    def baseline(self, event):
        if event in self.baselines:
            return self.baselines[event]
        cheap, cp, manifest = read_event(self.cheap, event, "cheap")
        ref, rp, _ = read_event(self.reference, event, "reference")
        if cheap["config"]["kwargs"]["nlive"] != 100 or ref["sampler_kwargs"]["nlive"] != 2000:
            raise ValueError("Wrong baseline live points")
        if cheap["likelihood_id"] != ref["comparison_audit"]["comparison_likelihood_id"]:
            raise ValueError("Baseline event/likelihood matching failed")
        if tuple(ref["search_parameter_keys"]) != PARAMETERS:
            raise ValueError("Baseline coordinate order mismatch")
        specs, ref_mass, cheap_jsd = {}, {}, {}
        for name in PARAMETERS:
            prior = ref["priors"][name]["kwargs"]
            spec = marginal_spec(rp[name].to_numpy(), prior["minimum"], prior["maximum"], prior.get("boundary") == "periodic")
            specs[name] = spec
            ref_mass[name] = marginal_mass(rp[name], spec)
            cheap_jsd[name] = js_divergence(marginal_mass(cp[name], spec), ref_mass[name])
        rng = np.random.default_rng(20261105+event)
        calibration = []
        if len(cp) >= len(rp):
            raise ValueError("Reference split calibration needs more reference than cheap draws")
        for _ in range(self.null_repeats):
            selected = rng.choice(len(rp), len(cp), replace=False)
            other = np.setdiff1d(np.arange(len(rp)), selected)
            calibration.append(float(np.mean([js_divergence(
                marginal_mass(rp[name].to_numpy()[selected], specs[name]),
                marginal_mass(rp[name].to_numpy()[other], specs[name])) for name in PARAMETERS])))
        row = {"event_id": event, "nis_status": "pending",
            "lnz_reference": ref["log_evidence"], "lnz_reference_error": ref["log_evidence_err"],
            "delta_lnz_cheap_reference": cheap["log_evidence"]-ref["log_evidence"],
            "delta_lnz_cheap_reference_error": float(np.hypot(cheap["log_evidence_err"], ref["log_evidence_err"])),
            "delta_lnz_nismo_reference": None, "delta_lnz_nismo_reference_error": None,
            "jsd_cheap_reference_bits": float(np.mean(list(cheap_jsd.values()))),
            "jsd_nismo_reference_bits": None,
            "jsd_marginals": {name: {"cheap_reference_bits": cheap_jsd[name], "nismo_reference_bits": None} for name in PARAMETERS},
            "reference_split_calibration": {"median_bits": float(np.median(calibration)),
                "p05_bits": float(np.quantile(calibration, .05)), "p95_bits": float(np.quantile(calibration, .95)),
                "repeats": self.null_repeats, "subset_rows": len(cp), "complement_rows": len(rp)-len(cp), "seed": 20261105+event},
            "cheap_rows": len(cp), "reference_rows": len(rp), "reference_original_rows": ref["original_posterior_rows"],
            "nis_weight_ess": None, "nis_recovery_iterations": None, "nis_plot": None,
            "marginal_estimator": specs,
            "sources": {"cheap_posterior_sha256": cheap["posterior_sha256"],
                "reference_posterior_sha256": ref["posterior_sha256"], "reference_original_result_sha256": ref["source_result_sha256"],
                "baseline_likelihood_id": cheap["likelihood_id"]}}
        self.baselines[event] = row, ref, ref_mass
        return self.baselines[event]

    def build(self, site_dir=None):
        rows = []
        for event in range(100):
            baseline, ref, reference_mass = self.baseline(event)
            receipt_path = self.campaign / "outcomes" / f"event_{event:03d}.json"
            receipt = read_receipt(receipt_path) if receipt_path.exists() else None
            signature = json.dumps(receipt, sort_keys=True)
            if event in self.cache and self.cache[event][0] == signature:
                row = self.cache[event][1]
            else:
                row = json.loads(json.dumps(baseline))
                if receipt:
                    row["nis_status"] = receipt["status"]
                    if receipt["status"] == "converged":
                        output = Path(receipt["output"])
                        comparison_path = output / "comparison.json"
                        if digest(comparison_path) != receipt["comparison_sha256"]:
                            raise ValueError("NIS comparison differs from campaign receipt")
                        comparison = json.loads(comparison_path.read_text())
                        if comparison["event"] != event or comparison.get("baseline_likelihood_id", comparison["likelihood_id"]) != row["sources"]["baseline_likelihood_id"]:
                            raise ValueError("NIS/reference event identity mismatch")
                        samples, weights = load_nis(output / "nis/result.npz", comparison, receipt["result_sha256"])
                        marginal_jsd = {}
                        for j, name in enumerate(PARAMETERS):
                            value = js_divergence(marginal_mass(samples[:, j], row["marginal_estimator"][name], weights), reference_mass[name])
                            marginal_jsd[name] = value
                            row["jsd_marginals"][name]["nismo_reference_bits"] = value
                        row.update(delta_lnz_nismo_reference=comparison["nis"]["log_evidence"]-ref["log_evidence"],
                            delta_lnz_nismo_reference_error=float(np.hypot(comparison["nis"]["log_evidence_err"], ref["log_evidence_err"])),
                            jsd_nismo_reference_bits=float(np.mean(list(marginal_jsd.values()))),
                            nis_weight_ess=float(1/np.sum(weights**2)),
                            nis_log_evidence=comparison["nis"]["log_evidence"],
                            nis_log_evidence_error=comparison["nis"]["log_evidence_err"],
                            nis_nlive=comparison["nis"]["nlive"], nis_weighted_rows=len(weights),
                            nis_sampler_seconds=comparison["nis"]["sampler_seconds"],
                            nis_recovery_iterations=comparison["nis"]["recovery_iterations"],
                            data_origin=comparison.get("data_origin", {"kind": "original_frozen"}))
                        row["sources"].update(nis_result_sha256=receipt["result_sha256"], nis_comparison_sha256=receipt["comparison_sha256"])
                        plot = output / "corner.png"
                        if not plot.exists() and receipt.get("reused"):
                            plot = self.campaign / "reused_artifacts/event_000_corner.png"
                        if plot.exists():
                            row["nis_plot"] = f"plots/nismo/injection_{event:03d}.png"
                            if site_dir:
                                target = Path(site_dir) / row["nis_plot"]
                                target.parent.mkdir(parents=True, exist_ok=True)
                                if not target.exists() or digest(target) != digest(plot):
                                    shutil.copyfile(plot, target)
                self.cache[event] = signature, row
            rows.append(row)
        paired = [row for row in rows if row["nis_status"] == "converged"]
        state = json.loads((self.campaign / "status.json").read_text())
        return {"schema_version": SCHEMA, "created_utc": datetime.now(timezone.utc).isoformat(),
            "event_count": len(rows), "nis_counts": dict(Counter(row["nis_status"] for row in rows)),
            "campaign_state": state["state"], "active_event": (state.get("active") or {}).get("event"),
            "method": {"id": METHOD, "jsd_log_base": 2, "jsd_unit": "bits", "jsd_range": [0, 1],
                "headline_jsd": "arithmetic mean of eight 1D marginal divergences; not joint 8D JSD",
                "density": "Gaussian-smoothed weighted histograms on common prior support; reflected nonperiodic and wrapped periodic boundaries",
                "bandwidth": "per-event, per-parameter reference Scott bandwidth shared by all three estimates; comparison only, never sampler training/tuning",
                "grid": "512–8192 bins, at least four bins per bandwidth unless the recorded floor binds",
                "calibration": "disjoint reference splits matching the cheap draw count; descriptive 5/50/95 percentiles, not confidence bounds or a bias correction",
                "limitations": ["Marginal JSD misses correlations and depends on density-estimation resolution.",
                    "Unequal sample sizes and correlated NIS particles affect JSD; the calibration only matches cheap sample size.",
                    "Reported evidence errors exclude sampler/proposal/recovery bias; stopping thresholds do not certify convergence.",
                    "Reference posteriors are thinned to 1000 retained draws per event; reference is finite-sampling, not exact truth."]},
            "paired_summary": {"events": len(paired),
                "mean_jsd_cheap_bits": float(np.mean([r["jsd_cheap_reference_bits"] for r in paired])) if paired else None,
                "mean_jsd_nismo_bits": float(np.mean([r["jsd_nismo_reference_bits"] for r in paired])) if paired else None,
                "median_abs_delta_cheap": float(np.median([abs(r["delta_lnz_cheap_reference"]) for r in paired])) if paired else None,
                "median_abs_delta_nismo": float(np.median([abs(r["delta_lnz_nismo_reference"]) for r in paired])) if paired else None},
            "source_hashes": {"cheap_archive": digest(self.cheap), "reference_archive": digest(self.reference),
                              "analysis_script": digest(__file__)}, "events": rows}


def export(data, output, site_dir=None):
    output = Path(output)
    atomic(output / "main_results.json", data)
    columns = ["event_id", "nis_status", "lnz_reference", "lnz_reference_error",
        "delta_lnz_cheap_reference", "delta_lnz_cheap_reference_error", "delta_lnz_nismo_reference", "delta_lnz_nismo_reference_error",
        "jsd_cheap_reference_bits", "jsd_nismo_reference_bits", "nis_weight_ess", "nis_recovery_iterations"]
    columns += [f"jsd_{method}_{name}_bits" for name in PARAMETERS for method in ("cheap", "nismo")]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    for row in data["events"]:
        flat = {key: row.get(key) for key in columns}
        for name in PARAMETERS:
            for method in ("cheap", "nismo"):
                flat[f"jsd_{method}_{name}_bits"] = row["jsd_marginals"][name][f"{method}_reference_bits"]
        writer.writerow(flat)
    atomic(output / "main_results.csv", stream.getvalue())
    if site_dir:
        target = Path(site_dir) / "data"
        atomic(target / "main_results.json", data)
        atomic(target / "main_results.js", "window.BBH_MAIN_RESULTS = "+json.dumps(data, separators=(",", ":"), allow_nan=False)+";\n")
        atomic(target / "main_results.csv", stream.getvalue())


def publish_git(site_dir, count):
    """Publish only generated data/plots from a dedicated clean checkout."""
    root = Path(site_dir).resolve().parent
    allowed = ["docs/data/main_results.json", "docs/data/main_results.js", "docs/data/main_results.csv", "docs/plots/nismo"]
    changed = subprocess.check_output(["git", "-C", str(root), "status", "--porcelain"], text=True).splitlines()
    if any(not any(line[3:].startswith(path) for path in allowed) for line in changed):
        raise RuntimeError("Publication checkout has unrelated changes; refusing to commit them")
    if changed:
        subprocess.run(["git", "-C", str(root), "add", "--", *allowed], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-m", f"Refresh main comparison results ({count}/100 NIS events)"], check=True)
        # Normal fast-forward push: concurrent changes are never overwritten.
        subprocess.run(["git", "-C", str(root), "push", "origin", "HEAD:main"], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("cheap", "reference", "campaign-root", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--site-dir", type=Path)
    parser.add_argument("--null-repeats", type=int, default=32)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=float, default=60.)
    parser.add_argument("--git-publish", action="store_true")
    args = parser.parse_args()
    if args.null_repeats < 1 or args.interval < 5 or (args.git_publish and not args.site_dir):
        parser.error("Invalid repeats/interval or missing site directory for publication")
    args.output.mkdir(parents=True, exist_ok=args.watch)
    with (args.output / "export.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        builder = MainResults(args.cheap, args.reference, args.campaign_root, args.null_repeats)
        last_published = -1
        while True:
            data = builder.build(args.site_dir)
            export(data, args.output, args.site_dir)
            count = data["nis_counts"].get("converged", 0)
            terminal = data["campaign_state"] in ("completed", "blocked", "stopped_after_current")
            if args.git_publish and (last_published < 0 or count-last_published >= 10 or terminal):
                publish_git(args.site_dir, count)
                last_published = count
            print(json.dumps({"as_of": data["created_utc"], "nis_counts": data["nis_counts"], "paired_summary": data["paired_summary"]}), flush=True)
            if not args.watch or terminal:
                break
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
