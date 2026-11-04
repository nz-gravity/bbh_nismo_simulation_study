#!/usr/bin/env python3
"""Recheck portable metadata for all pairs, without claiming original-file access."""
import argparse
import io
import json
import tempfile
import zipfile
from pathlib import Path

import bilby
import numpy as np
import pandas as pd

from local_morphnis import PARAMETERS, read_event, write_new


def close(a, b, atol=1e-13):
    if not np.isclose(a, b, rtol=8*np.finfo(float).eps, atol=atol):
        raise ValueError(f"Numeric metadata mismatch: {a} != {b}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cheap", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    with zipfile.ZipFile(args.cheap) as z:
        prefix = z.namelist()[0].split("/")[0]
        catalogue = pd.read_csv(io.BytesIO(z.read(prefix+"/catalogue/injections.csv")), float_precision="round_trip").set_index("inj_id")
        prior_bytes = z.read(prefix+"/configs/bbh.prior")
    if set(catalogue.index) != set(range(100)) or not catalogue.index.is_unique:
        raise ValueError("Catalogue IDs are not unique 0–99")
    with tempfile.NamedTemporaryFile(suffix=".prior") as file:
        file.write(prior_bytes)
        file.flush()
        priors = bilby.gw.prior.BBHPriorDict(file.name)
    events = []
    for event in range(100):
        cheap, cp, manifest = read_event(args.cheap, event, "cheap")
        ref, rp, _ = read_event(args.reference, event, "reference")
        config = manifest["scientific_config"]["settings"]
        injection = config["injection"]
        if cheap["config"]["kwargs"]["nlive"] != 100 or ref["sampler_kwargs"]["nlive"] != 2000:
            raise ValueError("Wrong sampler resolution")
        if tuple(ref["search_parameter_keys"]) != PARAMETERS:
            raise ValueError("Sampled coordinates differ")
        for key in catalogue.columns:
            close(injection[key], catalogue.loc[event, key])
        for key in PARAMETERS + ("mass_1", "mass_2"):
            stored = ref["priors"][key]
            current = priors[key]
            if stored["__name__"] != type(current).__name__:
                raise ValueError("Prior families differ")
            for attribute in ("minimum", "maximum"):
                close(stored["kwargs"][attribute], getattr(current, attribute))
            if stored["kwargs"].get("boundary") != current.boundary:
                raise ValueError("Prior boundary convention differs")
        for key in config["fixed_parameters"]:
            stored = ref["priors"][key]
            if stored["__name__"] != "DeltaFunction":
                raise ValueError("Fixed-parameter convention differs")
            close(stored["kwargs"]["peak"], injection[key])
        meta = ref["scientific_metadata"]
        if set(meta["interferometers"]) != set(config["detectors"]):
            raise ValueError("Detector network differs")
        for detector in meta["interferometers"].values():
            for key, value in injection.items():
                close(detector["parameters"][key], value)
        for key in ("duration", "sampling_frequency", "start_time"):
            close(meta[key], config[key])
        for key in ("waveform_approximant", "reference_frequency"):
            if meta["waveform_arguments"][key] != config[key]:
                raise ValueError("Waveform convention differs")
        for key in ("time", "phase", "distance"):
            if meta[key+"_marginalization"] != config["marginalization"][key]:
                raise ValueError("Marginalization convention differs")
        for key, expected in (("frequency_domain_source_model", "lal_binary_black_hole"),
                              ("parameter_conversion", "convert_to_lal_binary_black_hole_parameters")):
            if meta[key]["__name__"] != expected:
                raise ValueError("Source/parameter conversion differs")
        if meta["reference_frame"] != "sky" or meta["time_reference"] != "geocent":
            raise ValueError("Likelihood reference convention differs")
        close(cheap["log_noise_evidence"], ref["log_noise_evidence"], atol=1e-6)
        close(ref["log_evidence"], ref["log_bayes_factor"]+ref["log_noise_evidence"])
        audit = ref["comparison_audit"]
        if not audit["passed"] or audit["comparison_likelihood_id"] != cheap["likelihood_id"]:
            raise ValueError("Published matching audit failed")
        close(audit["stored_log_likelihood_to_full_offset"], ref["log_noise_evidence"], atol=1e-6)
        events.append({"event": event, "cheap_rows": len(cp), "reference_rows": len(rp),
            "reference_original_rows": ref["original_posterior_rows"],
            "likelihood_id": cheap["likelihood_id"], "metadata_checks_passed": True,
            "noise_evidence_difference": cheap["log_noise_evidence"]-ref["log_noise_evidence"]})
    result = {"scope": "Portable release metadata only; original OzSTAR files and queue uninspected",
        "event_count": len(events), "event_ids": [e["event"] for e in events],
        "n_training_rows": sum(e["cheap_rows"] for e in events),
        "min_training_rows": min(e["cheap_rows"] for e in events),
        "max_training_rows": max(e["cheap_rows"] for e in events), "events": events,
        "limitations": ["No new all-event likelihood replay in this metadata audit.",
            "Original reference strain bytes were not archived.",
            "Original full inference histories remain necessary for sampler ESS/convergence checks."]}
    write_new(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k != "events"}))


if __name__ == "__main__":
    main()
