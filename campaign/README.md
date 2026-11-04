# Local NISMO preflight

See [the local smoke-test results and limitations](LOCAL_STATUS.md).

This workflow uses `morphnis` from **nismo-dev**, not the separate `nismo`
distribution. It is a guarded local smoke-test workflow, not an OzSTAR
submission script. Existing baseline results and the published site are untouched.

Required sibling checkouts:

| Repository | Inspected commit |
| --- | --- |
| nz-gravity/nismo-dev | 7b945633964c068e094484f5ea55bf97a9ec97f5 |
| nz-gravity/bbh_sampler_benchmarks | de448a58fe27fec2a705dc9683f453ef18f98554 |
| nz-gravity/morphZ_casestudy_CBC_pe | 6fb36e226d216ebb20a2e9cd87397635b45b931e |
| Study baseline | 8f0c83f7a1bb0c9e9ce17508b078017155cf835d |

The benchmark repository contains original frozen event-0 strain arrays matching
the released likelihood identity. The compact study release contains all cheap
posterior draws, but only 1,000 reference draws per event. It excludes strain
arrays and nested histories. A thinned posterior is sufficient for a preliminary
overlay, but not to reconstruct the reference sampler's ESS or convergence.

From the study root, with Python 3.12 and `uv`:

```sh
uv venv --python 3.12 .venv-local
uv pip install --python .venv-local/bin/python -r campaign/requirements.txt
.venv-local/bin/python -m pytest -q campaign/test_local_morphnis.py
```

Download the two ZIPs from the `dynesty-baselines-2026-11-04` release into a
separate local directory. Run `scripts/verify_results.py` on each. The runner
also checks whole-archive and posterior hashes against the committed manifest.

Example with explicit external paths and a fresh output name:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv-local/bin/python scripts/local_morphnis.py 0 \
  --cheap "$CHEAP_ZIP" --reference "$REFERENCE_ZIP" \
  --benchmark-repo ../bbh_sampler_benchmarks --nismo-repo ../nismo-dev \
  --data ../bbh_sampler_benchmarks/data/bbh_strain.npz \
  --output "$NEW_OUTPUT_DIRECTORY"
```

Every invocation reserves its output directory exclusively before loading data.
Existing, incomplete and failed directories are all refused. There is no implicit
resume. The underlying NIS exporter replaces named files, so it is only called
inside this new reservation. Each attempt records versions, source revisions,
arguments, hashes, validation, sampling diagnostics and, where applicable, failure
details. The full NIS NPZ preserves weighted samples and traces without pickle.

## Scientific checks and frozen choices

- Input data and its manifest must match the original event checksum exactly.
  A regenerated realization is rejected even if a small likelihood replay agrees.
- Frozen data construction uses the original benchmark likelihood code and its
  exact four core versions. Detector geometry and noise likelihood are checked.
- Both cheap and independent reference posterior rows undergo 32-point prior and
  likelihood replays at tolerance `1e-6`. Only full likelihood or the documented
  noise-relative constant is accepted. The evidence values are already full;
  no noise offset is added to either baseline evidence.
- Train exclusively on cheap equal-weight draws in the stored eight-coordinate
  order. Every event has 81–128 draws. Set `thin=1` explicitly: the adapter's
  default 1,000-row cap for eight dimensions would not bind, but this avoids an
  implicit future change. Reference samples are never fitted or used to choose
  settings.
- Primary: NIS `nlive=100`, fit seed `20261104`, sampling seed `20262104`,
  `dlogz=0.1`, maximum 10,000 iterations, DE/stretch weights 0.8/0.2,
  DE adaptation enabled, default walk length 125 with minimum 5 acceptances,
  and at most 3 heuristic recovery retries. Resolved settings and all recovery
  attempts are retained in `nis/summary.json` and `nis/result.npz`.
- Prespecified stability probe for event 0: `nlive=200`, fit seed `20261105`,
  sampling seed `20262105`, `dlogz=0.05`, 200-step initial walks, no recovery
  retries, same 10,000-iteration cap. This is a different-seed/stricter-settings
  probe, not a controlled estimate of seed variance. It was launched before
  inspecting final evidence differences.
- `max_iterations` is a separate **non-converged** outcome with exit status 3.
  A caught exception is a failed outcome with traceback and available call counts.
  Recovery is heuristic and can bias endpoint selection; its use is reported.
- NIS weight ESS is Kish ESS of the stored quadrature weights. It does not account
  for chain correlations or missing modes. Baseline posterior draw counts are
  not presented as baseline ESS.
- Cost includes the cheap pilot plus NIS, with validation calls separately
  reported. Original sampling time, invocation time and core count retain their
  source meanings; cross-hardware wall times are not claimed as speedups.

`scripts/probe_local_reconstruction.py` reproduces the separate reconstruction
experiment in a fresh directory. A numerical replay and exact data identity are
recorded separately. It never starts inference.

`scripts/audit_public_metadata.py` checks the 100 portable catalogue pairs,
sampled/fixed priors, parameterization, detector/injection metadata, waveform and
marginalization conventions, and evidence/noise identities. Scalar metadata
use floating-point comparison; density/evidence identities use the documented
`1e-6` tolerance. This does not replace original-file validation.

`scripts/render_local_comparison.py --run RUN --output NEW_DIRECTORY` repairs or
regenerates figures from cached NPZ samples without likelihood evaluations or
modifying sampling output. It checks every diagonal density integral.

## Full campaign prerequisites

Before any 100-event campaign, inspect the actual original catalogue/result
layouts, current queue and existing outputs. Obtain original frozen inputs for
all events and unthinned `nlive=2000` results, make a one-to-one manifest, and
repeat injection/prior/waveform/likelihood checks against those files. Retain
unknown reference sampler seeds as unknown. No scheduler job has been submitted
by these local scripts. Use the completed smoke-test resource measurements to
choose resources, and gate submission on validation and duplicate-job checks.
