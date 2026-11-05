# BBH NISMO simulation study

The [comparison webpage](https://nz-gravity.github.io/bbh_nismo_simulation_study/)
reports the matched reference lnZ, cheap/NISMO evidence differences and posterior
JSD. The [main-result script and definitions](campaign/MAIN_RESULTS.md) preserve
the reproducible calculation. In-progress NISMO results are explicitly partial.

Dynesty parameter-estimation baselines for **100 matched BBH injections**, IDs **0–99**.

| Dataset | Live points | Retained posterior draws | Original saved draws |
|---|---:|---:|---:|
| Cheap | 100 | 9,911 | 9,911 |
| Reference | 2,000 | 100,000 | 923,335 |

The selected reference is **nlive=2000, not nlive=4000**. These packages contain Dynesty baselines, not NISMO sampler outputs.

## Downloads and plots

Download both result packages, checksum sidecars, the portable manifest and Python verifier from the [versioned data release](https://github.com/nz-gravity/bbh_nismo_simulation_study/releases/tag/dynesty-baselines-2026-11-04). Browse the [100-event corner comparison website](https://nz-gravity.github.io/bbh_nismo_simulation_study/), or inspect the static source and plots in `docs/`. Each event overlays cheap and reference posteriors on shared axes.

## Samples and matching

All cheap saved draws are retained. Reference events retain 1,000 draws each, selected uniformly without replacement using PCG64 selection seed 0; exact source-row indices and original counts are recorded. This selection seed is distinct from the original reference sampler seeds, which were not recorded.

The 100 pairs pass injection/prior checks, noise-evidence checks and 32 posterior-point likelihood/prior replays per reference event. Full-inference evidence/error and cost metrics are retained without recomputation from thinned samples. Stored posterior likelihood columns can be ratios relative to noise; per-event metadata documents the offset for full likelihood. Evidence values are already full evidence.

Each package includes portable scientific settings, event identities, checksums and necessary provenance. Private machine paths and operational job details are excluded. Matching is not a convergence or coverage certificate.
