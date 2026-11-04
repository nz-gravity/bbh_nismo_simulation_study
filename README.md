# BBH NISMO simulation study

Dynesty parameter-estimation baselines for **100 matched BBH injections**, IDs **0–99**.

| Dataset | Live points | Retained posterior draws | Original saved draws |
|---|---:|---:|---:|
| Cheap | 100 | 9,911 | 9,911 |
| Reference | 2,000 | 100,000 | 923,335 |

The selected reference is **nlive=2000, not nlive=4000**. These packages contain Dynesty baselines, not NISMO sampler outputs.

## Downloads and plots

Versioned result ZIPs, SHA-256 checksums and a standard-library Python verifier are prepared for release. Publication is pending; no download assets or hosted website are available yet. The static comparison website is prepared in `docs/` and shows shared-axis cheap/reference corner overlays by injection ID.

## Samples and matching

All cheap saved draws are retained. Reference events retain 1,000 draws each, selected uniformly without replacement using PCG64 selection seed 0; exact source-row indices and original counts are recorded. This selection seed is distinct from the original reference sampler seeds, which were not recorded.

The 100 pairs pass injection/prior checks, noise-evidence checks and 32 posterior-point likelihood/prior replays per reference event. Full-inference evidence/error and cost metrics are retained without recomputation from thinned samples. Stored posterior likelihood columns can be ratios relative to noise; per-event metadata documents the offset for full likelihood. Evidence values are already full evidence.

Each package includes portable scientific settings, event identities, checksums and necessary provenance. Private machine paths and operational job details are excluded. Matching is not a convergence or coverage certificate.
