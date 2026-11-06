#!/usr/bin/env python3
"""Make two weighted posterior projections without new likelihood calls."""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import gaussian_filter

from local_morphnis import PARAMETERS, read_event, write_new


def quantiles(x, weights):
    order = np.argsort(x)
    return np.interp([.001, .999], np.cumsum(weights[order])/weights.sum(), x[order])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a fresh output filename")
    inv = json.loads((args.run/"invocation.json").read_text())["arguments"]
    event = inv["event"]
    _, cheap, _ = read_event(inv["cheap"], event, "cheap")
    reference, ref, _ = read_event(inv["reference"], event, "reference")
    with np.load(args.run/"nis/result.npz", allow_pickle=False) as saved:
        x = np.concatenate((saved["dead_theta"], saved["final_live_theta"]))
        w = np.exp(saved["log_posterior_weights"])
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.3), constrained_layout=True)
    receipt = []
    series = [(ref[list(PARAMETERS)].to_numpy(), np.ones(len(ref))/len(ref), "Dynesty 2000", "#222222", "--"),
              (cheap[list(PARAMETERS)].to_numpy(), np.ones(len(cheap))/len(cheap), "Cheap Dynesty", "#2166ac", ":"),
              (x, w, "DE/rwalk NISMO", "#28814c", "-")]
    for ax, (j, k) in zip(axes, [(0, 1), (0, 2)]):
        bounds = []
        for index in (j, k):
            limits = np.array([quantiles(t[:, index], p) for t, p, *_ in series])
            low, high = limits[:, 0].min(), limits[:, 1].max()
            prior = reference["priors"][PARAMETERS[index]]["kwargs"]
            bounds.append((max(prior["minimum"], low-.05*(high-low)),
                           min(prior["maximum"], high+.05*(high-low))))
        dx = [(b-a)/180 for a, b in bounds]
        bandwidth = np.array([ref[PARAMETERS[t]].std() for t in (j, k)])*len(ref)**(-1/6)
        for t, p, label, color, style in series:
            h, ex, ey = np.histogram2d(t[:, j], t[:, k], bins=180, range=bounds, weights=p/p.sum())
            included = float(h.sum())
            h = gaussian_filter(h, [max(.7, bandwidth[a]/dx[a]) for a in range(2)], mode="reflect")
            h /= h.sum()
            ordered = np.sort(h.ravel())[::-1]
            levels = sorted({float(ordered[np.searchsorted(np.cumsum(ordered), mass)]) for mass in (.5, .9)})
            ax.contour((ex[:-1]+ex[1:])/2, (ey[:-1]+ey[1:])/2, h.T,
                       levels=levels, colors=[color], linestyles=style, linewidths=1.4)
            receipt.append({"parameters": [PARAMETERS[j], PARAMETERS[k]], "sampler": label,
                            "displayed_mass": included, "range": bounds})
        ax.set(xlabel=PARAMETERS[j], ylabel=PARAMETERS[k])
        ax.ticklabel_format(axis="x", style="plain", useOffset=False)
    fig.legend([Line2D([], [], color=c, ls=s) for c, s in [("#222222", "--"), ("#2166ac", ":"), ("#28814c", "-")]],
               [item[2] for item in series], loc="outside upper center", ncol=3,
               title=f"Event {event}: two posterior projections · displayed 50% and 90% contours")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180, bbox_inches="tight")
    plt.close(fig)
    write_new(args.output.with_suffix(".json"), {"display": "Common bounds from 0.1–99.9% weighted ranges plus padding, clipped to prior support; common reference Scott smoothing.", "series": receipt})


if __name__ == "__main__":
    main()
