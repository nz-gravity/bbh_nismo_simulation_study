# Local BBH NISMO smoke test — 4 November 2026

Two event-0 NIS runs reached their stopping threshold using original,
checksum-matched frozen strain data. Their evidence estimates are compatible
with the independent 2,000-live reference at the reported statistical precision.
Posterior differences and a failed recovery-free probe prevent treating this
as a validated production campaign. **No cluster jobs or full 100-event campaign
were launched.**

| Event 0 method | log evidence ± reported error | Weight ESS | Outcome | Recovery retries |
| --- | --- | ---: | --- | ---: |
| Cheap Dynesty, 100 live | −16169.8489 ± 0.6943 | unavailable | published baseline | unavailable |
| Reference Dynesty, 2,000 live | −16170.6467 ± 0.1020 | unavailable | published baseline | unavailable |
| NIS primary, 100 live | −16170.7327 ± 0.2722 | 543.6 | `dlogz` | 2 |
| NIS repeat, 100 live | −16171.0053 ± 0.2732 | 634.4 | `dlogz` | 1 |
| NIS strict probe, 200 live | no final estimate | unavailable | failed at iteration 1,607 | disabled |

NIS minus reference is **−0.0860 ± 0.2906** for the primary and
**−0.3586 ± 0.2916** for the repeat. Difference errors combine the two reported
errors in quadrature, assuming independent sampling noise. These errors do not
bound sampler/proposal bias, correlations, or missing modes. The reference is a
finite-sampling comparison, not exact truth. Baseline posterior draw counts are
not ESS; NIS weight ESS also does not account for chain correlation.

The strict probe accepted only 4 of the required 5 moves in a 300-proposal walk
and stopped without a final result. Its initial walk length was 200 and was
adapted between walks. The successful runs used heuristic recovery, so the
failure is material to assessing their reliability. Longer, independently
validated walks or another replacement strategy should be investigated before
production; no settings were selected by optimizing against reference evidence.

## Posterior comparisons

[Primary corner overlay](figures/event_000_primary/corner.png) ·
[Different-seed overlay](figures/event_000_repeat/corner.png)

Both use common axes, separately normalized marginal densities, 50%/90%
contours, and original weighted NIS samples. Injection truth is gray. The cheap
posterior contains all 104 saved draws; the reference overlay uses 1,000 draws
selected from 9,981 original draws. No reference draw trained the proposal.

The primary's `phi_jl` marginal differs visibly from the reference. Its
descriptive Wasserstein distance is 0.634 radians, versus 0.149 for the repeat
and 0.095 for cheap Dynesty. Angular distances use a common seam centered on the
reference circular mean; they are not circular optimal-transport metrics or
significance tests. Other marginals also differ. Two seeds do not establish
coverage or separate sampling variance from bias.

The [per-run JSON receipts](results/) contain all parameter distances, training
choices, seeds, likelihood/prior audits and cost counters. The two compressed
`result.npz` files retain the full NIS samples, weights and traces. Their
quadrature sums and posterior-weight normalization were checked separately.

## Computational cost

| Attempt | New sampler likelihood calls | Sampler time | Cheap pilot + this attempt, likelihood calls |
| --- | ---: | ---: | ---: |
| NIS primary | 322,385 | 291.6 s | 629,924 |
| NIS repeat | 255,446 | 234.6 s | 562,985 |
| Failed strict probe | 302,998 | 283.0 s including setup/fit/audit | 610,537 |

The cheap pilot reported 307,539 likelihood evaluations, 218.0 sampling seconds,
44.5 invocation seconds and 2 cores. These time fields differ in their source
semantics and are retained separately. Primary/repeat fitting took 23.0/0.44 s;
these costs are additional to sampler time. Each attempt also made 64 validation
likelihood calls. Reference Dynesty reported 108,664,994 likelihood evaluations
and 22,556.4 sampling seconds. Counters and hardware differ; these values are not
a demonstrated wall-clock speedup. Do not charge the shared pilot twice when
aggregating repeated attempts.

## Validation and remaining inputs

- Both released ZIPs passed the published checksum/member/sample verifier.
- All 100 pairs passed a new portable-metadata check of catalogue/injection,
  priors, parameter order, detector network, waveform, likelihood reference,
  marginalization, and evidence conventions. The largest noise-evidence
  difference was `1.01e-8`, below the documented `1e-6` replay tolerance. This was
  a metadata audit, not a new all-event likelihood replay.
- On original frozen event-0 data, 32 cheap and 32 held-out reference points
  replayed with prior residual at most `8.9e-16` and likelihood residual at most
  `3.7e-12`. The stored likelihoods are noise-relative; the full-likelihood
  offset is about `−16293.35836458472`. Baseline evidence is already full and was
  not shifted again.
- The local frozen target uses Bilby 2.8.0 / LALSuite 7.26.15; the historical
  reference records Bilby 2.7.1 / LALSuite 7.26.1. The event-0 numerical replay
  passes despite this version difference; it is not a global equivalence proof.
- Local regenerations of events 0, 48 and 99 replayed 32 cheap posterior points
  per event within `3.7e-12`, but failed the original strain-byte checksums.
  Event-0 array inspection found strain differences up to `8.32e-39`; frequency
  and PSD arrays matched. Regenerated data were not used for NIS inference.
- 53 relevant upstream tests passed in the actual pinned campaign environment;
  the added scientific/safety suite now has 4 passing tests. Integration checks refused an existing
  output directory and changed data. A deliberate one-iteration run returned
  `non_converged`, `max_iterations`, exit code 3; it is excluded from science
  comparisons.
- The first sampler result was saved before a plotting compatibility error.
  The error and original output remain intact. Corrected plots were rebuilt
  from cached samples with zero likelihood calls. All 24 diagonal density
  integrals per overlay equal one within numerical tolerance; both figures were
  visually inspected.

The saved results needed for training and the core comparison are already
available for all 100 events: complete cheap training draws, reference posterior
subsets, and full-inference evidence/error/cost values. Unthinned reference files
and sampler histories would improve diagnostics, but are not prerequisites for
that comparison. The earlier statement that full reference files were required
was too broad.

Original frozen inputs for the other 99 events, original result layouts and
cluster queue state remain unavailable locally. This limits original-byte
replication and cluster duplicate checks. Numerically validated local
reconstruction is a separate route; byte-checksum differences alone do not
establish a scientific mismatch. The original reference strain bytes were not
archived, so matching remains a documented numerical check.

### Follow-up: all 100 local reconstructions validated

After rechecking all three repositories, local reconstruction was tested for
every event against **all 9,911 cheap posterior rows** and **32 held-out
reference rows per event** (3,200 reference replays). All 100 numerical
likelihood/prior contracts passed at the documented `1e-6` tolerance. Maximum
absolute likelihood residual was `1.06e-8`, prior residual `3.56e-15`, and
noise-likelihood difference `1.01e-8`. See the
[summary](results/reconstruction_audit_all100_summary.json) and
[per-event receipts](results/reconstruction_audit_all100_events.json).

None of the regenerated strain files matched the original byte checksums.
They remain explicitly labelled reconstructions; the numerical agreement does
not establish exact bytes, global equivalence, or sampler convergence. No new
NIS inference was launched during this follow-up. These checks support
continuing the scientific workflow locally; missing unthinned reference files
are not a blocker for the core evidence/posterior comparison. The remaining
NIS stability questions are separate from baseline-result availability.

The linked `EL-MZ/MorphZ/analysis/LIGO/fast_pp` directory was checked at commit
`9993081c3ddd60be7d6b34be8b76ffd95a445fb2`. It contains reconstruction scripts,
catalogue, priors, aggregate evidences and plots, rather than per-event raw
strain/result files. Its injection catalogue, prior file and setup script have
identical Git blob IDs to the inspected reference-study checkout. The benchmark
repository still contains a single frozen event-0 dataset, while the simulation
study's release contains the 100 matched baseline pairs.

The portable [validation receipt](results/validation_receipt.json) records
scope and guard outcomes. [Workflow commands and fixed settings](README.md)
describe reproduction. The complete private local run directory retains command
arguments, original logs, code snapshots, environment freeze and failed attempts.
