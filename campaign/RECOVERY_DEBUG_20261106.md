# Events 23 and 47: replacement and weight audit, 6 November 2026

**The full campaign rerun is on hold.** Event 47 failed the preset fixed-walk, no-retry control. No failed-run posterior was exported. All original 100-event results remain unchanged and are exploratory pending sampler validation.

Reconnected to UOA484808. Here, 23/47 are catalogue event IDs; sampler RNG seeds are recorded separately. All positive-weight saved points were replayed: 717 for event 23 and 3,307 for event 47. Likelihood/prior residuals were zero; proposal-density discrepancies were below 1.9e-13, pseudo-likelihood identity discrepancies below 3.7e-12, and normalized-weight discrepancies below 1.3e-14. No weight-bookkeeping bug was found. Kish ESS was 611 and 1,795, respectively; those values do not measure correlations or missing modes. Original recovery retries were 1 and 40.

The kernel targets q(theta) times the strict pseudo-likelihood constraint, with pseudo-likelihood L*pi/q. Local Metropolis acceptance includes the proposal-density ratio, and stretch moves include the dimension-dependent Hastings correction. The default campaign mixture uses a frozen complementary donor bank. Saved quadrature and normalization agree with independent recalculation.

Recovery restarts failed walks and selects a successful endpoint. This can change the endpoint distribution. For example, a two-state MH chain targeting (0.9, 0.1) with a symmetric flip proposal has acceptance probabilities 1/9 and 1. Conditioning on an accepted move gives equal endpoint masses. This is a counterexample to successful-movement selection preserving a target, not proof that retries alone caused event 47's discrepancy.

The core safety patch changes the default from three retries to zero and adds a regression test. The local runner requires an explicit `--allow-heuristic-recovery` flag for retries, supports fixed walk settings, selects and verifies `--nismo-repo`, and records source hashes. This prevents silently reporting a recovered run as validated; it does not cure poor mixing.

## Controls and results

Same cheap training and fit seeds as the original runs; no reference training or tuning. NIS live points=100, dlogz=0.1, maximum iterations=10,000. Event 23 used exact independent rejection replacements from the same fixed Morph proposal; event 47 used 1,000 fixed proposals per walk, DE/stretch weights 0.8/0.2, gamma=0.595, five required accepted moves, adaptation disabled and retries=0. The diagnostic proposal budget was one million. Every control is retained.

| Event | Run | ΔlnZ vs reference | Mean marginal JSD [bits] | Likelihood calls | Seconds | Outcome |
|---|---|---:|---:|---:|---:|---|
| 23 | original | +0.104 ± 0.151 | 0.00729 | 86140 | 70.1 | stopping_threshold_reached |
| 47 | original | +0.954 ± 0.428 | 0.13782 | 454210 | 452.9 | stopping_threshold_reached |
| 23 | event023_rejection_001 | +0.081 ± 0.146 | 0.00103 | 40150 | 49.1 | stopping_threshold_reached |
| 23 | event023_rejection_002 | +0.118 ± 0.152 | 0.00231 | 55249 | 69.8 | stopping_threshold_reached |
| 47 | event047_fixed1000_001 | unavailable | unavailable | 343319 | 337.9 | failed |

Times are local sampler times for completed runs and total invocation time for the failed control. Calls exclude target validation and fitting; comparison.json also records the cheap pilot-inclusive calls for completed runs. The original event-23 and event-47 pilots cost 7,309 and 204,409 likelihood calls. Each diagnostic invocation also performs independent target replays; these extra calls are recorded in its validation.json. Evidence error bars combine reported NIS/reference statistical errors in quadrature; they do not include sampler/proposal bias. Reference lnZ values are -16127.449781 and -16210.925402. Cheap/reference mean marginal JSDs are 0.010286 and 0.035698 bits.

Event 23's independent controls completed in 49 and 70 seconds and improved the posterior agreement. They support local-walk sampling error as a contributor in this event. They do not establish eight-dimensional joint agreement or prove all events unbiased. Event 47 stopped at replacement 571 after 4/5 required moves in 1,000 proposals (7 constraint passes), using 343,319 likelihood calls in 337.9 seconds including validation and fitting. This is a failed sampling outcome, not a completed posterior. Increasing a limit or relaxing the movement test merely to get an output would not validate the sampler.

The existing 100-event snapshot has mean marginal JSD 0.06920 for NISMO versus 0.03132 for cheap Dynesty, despite smaller median absolute evidence differences (0.3487 versus 0.8374). It must not be presented as established NISMO posterior improvement.

## Validation gate and next work

No full rerun was launched. Before launching one, the replacement scheme needs reliable controls on a difficult target such as event 47, including independent constrained-draw benchmarks, posterior shape/correlation diagnostics and repeated seeds. A more informative cheap-only proposal or a validated constrained sampler may be needed. The present evidence does not identify a unique root cause between finite-walk mixing, recovery selection, rare proposal tails and missed modes. Removing retries is a safety fix, not a claim that the posterior problem is solved.

Tests: 132 focused core passes; 334 whole-suite passes, with three notebook-output failures reproduced on the unchanged base checkout; 11 study tests pass. Checkout selection was additionally validated with an event-23 target audit using the patched worktree. No old output directory was reused.

## Reproduction and artifacts

- Core base: `7b945633964c068e094484f5ea55bf97a9ec97f5`; local fix commit: `6e1fe5f741366815a6ff580063032236581c1404`.
- Apply [the core patch](patches/morphnis-fail-fast-recovery-20261106.patch) to that base in a separate worktree.
- [Machine-readable comparison](results/recovery_debug_20261106/comparison.json), [CSV](results/recovery_debug_20261106/comparison.csv), [weight replay audit](results/recovery_debug_20261106/weight_audit.json), [versions, code hashes and settings](results/recovery_debug_20261106/provenance.json).
- Scripts: `scripts/audit_saved_nis.py`, `scripts/debug_replacement_control.py`, `scripts/summarize_replacement_controls.py`; webpage metric implementation remains `scripts/build_main_results.py`.
- Local raw artifacts are under the existing campaign root, `debug_20261106/`: each control has invocation.json, validation.json, control.json, logs, and either a native result/comparison/corner or failure.json. Exact original receipts are hashed in the replay audit. Commands use the pinned benchmark .venv Python and one BLAS/OMP thread.

```sh
python scripts/audit_saved_nis.py --campaign "$ORIGINAL_CAMPAIGN" --event 23 --event 47 --output "$FRESH_AUDIT_JSON"
python scripts/debug_replacement_control.py 23 --campaign "$ORIGINAL_CAMPAIGN" --nismo-repo "$PATCHED_NISMO" --output "$FRESH_EVENT23" --mode rejection --seed 20261106
python scripts/debug_replacement_control.py 23 --campaign "$ORIGINAL_CAMPAIGN" --nismo-repo "$PATCHED_NISMO" --output "$FRESH_EVENT23_REPEAT" --mode rejection --seed 20261107
python scripts/debug_replacement_control.py 47 --campaign "$ORIGINAL_CAMPAIGN" --nismo-repo "$PATCHED_NISMO" --output "$FRESH_EVENT47" --mode fixed-walk --walk-steps 1000 --seed 20261106
python scripts/summarize_replacement_controls.py --campaign "$ORIGINAL_CAMPAIGN" --cheap "$CHEAP_ZIP" --reference "$REFERENCE_ZIP" --control "$FRESH_EVENT23" --control "$FRESH_EVENT23_REPEAT" --control "$FRESH_EVENT47" --output "$FRESH_SUMMARY"
```

See the [web diagnostic page](https://nz-gravity.github.io/bbh_nismo_simulation_study/recovery-debug.html) for overlays. The reference remains an independent finite-sample benchmark with 1,000 retained posterior draws, not exact truth.
