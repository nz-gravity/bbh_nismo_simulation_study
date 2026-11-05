# Main webpage result: evidence and posterior shape

The reproducible entry point is [`scripts/build_main_results.py`](../scripts/build_main_results.py).
It reads the released cheap/reference ZIPs and immutable sequential-campaign
receipts plus cached NIS NPZ files. It performs **zero new likelihood calls**
and never changes sampler inputs, settings, outputs, or job order.

| Main field | Definition |
| --- | --- |
| Reference lnZ | Stored full evidence for matched Dynesty `nlive=2000` |
| Cheap ΔlnZ | `lnZ_cheap − lnZ_reference` |
| NISMO ΔlnZ | `lnZ_nismo − lnZ_reference` |
| Cheap posterior JSD | Mean of 8 marginal `JSD(cheap, reference)` values |
| NISMO posterior JSD | Mean of 8 marginal `JSD(weighted NIS, reference)` values |

lnZ uses natural logarithms. Positive ΔlnZ means higher evidence than the
reference. Reported difference uncertainty is
`sqrt(sigma_method**2 + sigma_reference**2)`, assuming independent sampling
noise. It does not account for sampler/proposal/recovery bias. Reference is
finite-sampling, not exact truth.

JSD is `0.5 KL_2(P||M) + 0.5 KL_2(Q||M)`, with `M=(P+Q)/2`, in **bits**.
It lies between 0 and 1. This is divergence, not the square-root distance
returned by [SciPy's jensenshannon](https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.distance.jensenshannon.html).
The main number is explicitly a mean of marginal divergences, not an 8D joint
divergence. Each individual marginal is retained in JSON/CSV and on the webpage.
Parameter correlations are not assessed by marginal JSD.

## Density estimator and finite-sample interpretation

All three marginal estimates use the same per-event, per-parameter bandwidth:
the reference marginal standard deviation times `n_reference**(-1/5)` (Scott's
rule). This is comparison density estimation, not proposal fitting or sampler
tuning. For periodic φ angles, scale is computed from circularly centered
coordinates and smoothing wraps on the original 0–2π domain. Nonperiodic
boundaries reflect. All inputs are histogrammed on common full prior support,
then Gaussian-smoothed, using 512–8,192 bins and a bandwidth floor recorded in
the JSON. At least four bins resolve each bandwidth unless that floor applies.
NIS uses its original normalized quadrature weights without resampling. The
estimator is named `shared-reference-scott-smoothed-histogram-v1` in the output.

Every cheap posterior row and all 1,000 retained reference rows are used.
Reference sampling uncertainty and density smoothing affect the comparison.
The script adds a reference-split calibration: 32 disjoint random splits per
event, with the small split matching the cheap row count and the complement
forming the comparison. The 5/50/95 percentiles of the mean marginal JSD are
descriptive finite-sample calibration, **not** a confidence interval on the
observed JSD, a significance test, or a subtraction-based bias correction.
It only matches cheap sample size; weighted NIS ESS ignores correlations.

Only primary outcomes marked `converged` by the numerical stopping rule enter
the main NIS fields. Pending, failed and `max_iterations` cases retain explicit
states and missing values; they are not converted to zero. Summaries comparing
the two methods use the same paired completed-event cohort, while all 100
cheap/reference rows remain available.

## Rebuild and keep the site current

Run in the pinned campaign environment, with explicit input paths:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PINNED_PYTHON scripts/build_main_results.py \
  --cheap CHEAP_ZIP --reference REFERENCE_ZIP \
  --campaign-root SEQUENTIAL_CAMPAIGN --output NEW_DERIVED_OUTPUT \
  --site-dir docs
```

Outputs are `main_results.json`, `main_results.csv`, and the site's matching JS
payload. The site receives only portable scientific values, settings and hashes;
private source paths and process identifiers are excluded. Available NIS corner
overlays are copied into a new `docs/plots/nismo/` directory. Existing baseline
plots are preserved. Source NPZ and comparison hashes are checked before use.

`--watch` caches unchanged inputs/results, checks every 60 seconds and exits
after a terminal campaign state. An exclusive exporter lock prevents duplicate
watchers for the same derived output directory. `--git-publish` is intended for
a **dedicated clean publication worktree**: it commits only generated main-result
data and NIS plots, publishing initially, after each 10 additional completed
NIS events, and at campaign completion/stop. Pushes are ordinary fast-forward
pushes to `main`; unrelated changes or a concurrent main update stop publication
rather than being overwritten. The NIS worker/controller remain unaffected.

Tests in `campaign/test_main_results.py` check divergence units, analytic
Gaussian agreement, normalized weights, circular wrapping, support and cached
result integrity. Additional actual-data spot checks integrated reflected and
wrapped Gaussian kernels analytically for events 0 and 28 (chirp mass and
`phi_jl`, both methods); the largest difference from the gridded estimator was
0.000401 bits. These are spot checks, not a global estimator-accuracy bound.
