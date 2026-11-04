#!/usr/bin/env python3
"""Render cached NIS output into a fresh directory without any likelihood calls."""
import argparse
import json
from pathlib import Path

from morphnis import NISResult
from local_morphnis import digest, plot_corner, read_event, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    invocation = json.loads((args.run / "invocation.json").read_text())["arguments"]
    _, cheap, manifest = read_event(invocation["cheap"], invocation["event"], "cheap")
    _, reference, _ = read_event(invocation["reference"], invocation["event"], "reference")
    result = NISResult.load(args.run / "nis")
    validation = plot_corner(args.output, result, cheap, reference, manifest, invocation["event"])
    write_new(args.output / "render_validation.json", {
        "source_result_sha256": digest(args.run / "nis/result.npz"),
        "source_comparison_sha256": digest(args.run / "comparison.json"),
        "renderer_sha256": digest(Path(__file__).parent / "local_morphnis.py"),
        "source_run_label": f"{args.run.parent.name}/{args.run.name}",
        "sampler_termination_reason": result.termination_reason,
        "likelihood_calls": 0, **validation})
    print(args.output / "corner.png")


if __name__ == "__main__":
    main()
