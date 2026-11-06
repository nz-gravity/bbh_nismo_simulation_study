# Mehdi demo rerun: DE/rwalk 80/20, 6 November 2026

The requested configuration completed smoke events 47 and 23. Likelihood/prior replays and density/weight identities pass. The full fixed-setting 100-event sampler benchmark has been launched under the existing request; event 47 still has a posterior-quality alert. These are provisional sampler-performance results, not a claim of validated unbiased inference. The controller resumes the same immutable plan, verifies existing receipts and skips completed jobs. Live campaign state and counts are on the [comparison webpage](https://nz-gravity.github.io/bbh_nismo_simulation_study/).

## Fixed settings

- Source: `nz-gravity/nismo-dev` commit `1c0b92a4c2db7174f34afd566049961d6fbdb0bf`, isolated unchanged worktree. This commit adds an LVK random-walk pilot demo; the core NIS sampler is unchanged relative to the previously inspected base.
- User-specified post-processing: Morph phase enabled with 100,000 proposals; NIS live points 100; adaptive DE; fixed DE/rwalk weights 80/20, stretch 0; move-weight adaptation off. Rwalk scale adaptation uses the core default.
- No bandwidth override is supplied. The executable demo default resolves to `bandwidth_scale=2`; this differs from a fixed `--bw 2` and from the generic Morph fit default scale 1. README examples disagree with some executable defaults, so settings are resolved from code.
- All saved rows from each original cheap nlive=100 posterior train Morph, `thin=1`, with no training cap. The new random-walk pilot stage is skipped: this is post-processing of the existing cheap runs. The 2,000-live reference remains independent and is excluded from fitting and tuning.
- `dlogz=0.1`, maximum 10,000 iterations (a distinct non-converged outcome if reached); fit seed `20261104+event`, sampling seed `20262104+event`. All output directories are fresh.
- Upstream bounded recovery allows three retries. It is explicitly opted into and recorded as heuristic; it can bias endpoints. Successful numerical stopping is not a convergence, mixing or coverage certificate.
- Use the original pinned model environment so reconstructed likelihoods retain the original conventions. Fresh target replays bind each event to its audited reconstruction. Exact raw strain-byte replication is not claimed.

## Initial results

| Event | Reference lnZ | Cheap ΔlnZ | NISMO ΔlnZ ± statistical error | NISMO mean marginal JSD [bits] | Maximum correlation discrepancy | Calls including pilot | NIS seconds | Retry attempts |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 47 | -16210.925402 | +1.0356 | +0.2618 ± 0.2953 | 0.038960 | 0.475 | 408075 | 194.3 | 3 |
| 23 | -16127.449781 | +0.1534 | -0.2798 ± 0.1828 | 0.002068 | 0.110 | 41134 | 29.4 | 2 |

Reference lnZ uses natural logarithms; ΔlnZ is method minus reference. Difference errors combine reported statistical errors in quadrature and exclude possible proposal, recovery and sampler bias. Mean JSD averages eight weighted 1D marginal divergences; it is not joint 8D JSD. Correlation discrepancies are descriptive diagnostics, including a common circular seam for angular coordinates; alert thresholds are not calibrated significance tests. The reference retains 1,000 draws per event and is not exact truth.

Event 23 improved from original NISMO mean marginal JSD 0.007291 to 0.002068 (cheap/reference 0.010286). Event 47 improved from 0.137819 to 0.038960, but cheap/reference is 0.035698 and joint-shape differences remain. Evidence agreement and Kish ESS alone do not establish posterior correctness. The diagnostic alerts use fixed thresholds of mean marginal JSD >0.03 bits or maximum correlation discrepancy >0.25; all raw values remain available.

The two smoke results replayed all 2,010 positive-weight points: likelihood and prior residuals were zero, proposal-density residual <=7.2e-14, pseudo-likelihood identity residual <=3.7e-12, normalized-weight residual <=4.4e-15. All points were unique. ESS was 674 and 575, with 3 and 2 retry attempts; these ESS values omit chain correlations.

All 100 immutable jobs are planned in order 47, 23, 0, 1, … . The controller stops after two new outcomes for inspection; a restart verifies receipts and skips completed jobs. The original 100-event dataset and earlier controls remain separate selectable snapshots on the webpage. Failed, pending and iteration-limited outputs remain missing in the main NIS quantities.

An independent event-47 repeat under the final DE/rwalk 100k-pool recipe used sampling seed 20263151 with the same fit seed. It completed in 184.6 seconds with 191,837 likelihood calls; mean marginal JSD versus reference was 0.03940, maximum correlation discrepancy 0.490. Its seed-to-seed mean marginal JSD versus the prescribed primary was 0.05801. This repeat remains separate and does not replace the primary event-47 result.

## Earlier controls are retained

Before the final DE/rwalk instructions, the demo default DE/stretch mixture and 200,000-point pool was tested with retries disabled. Both events exhausted the pool and failed their first local walk. Allowing the upstream three retries completed two event-47 controls, with mean marginal JSD 0.02781 and 0.02746; their seed-to-seed JSD was 0.04259 and maximum correlation differences were 0.431 and 0.578. Those are separate diagnostics, not replacements for the prescribed primary runs or a best-seed selection.

The documented fixed `--bw 4` option was checked using 100,000 unconditioned proposal draws per event, without new likelihood calls. Only 0.744% (event 47) and 0.032% (event 23) landed inside the prior box. It was not used for inference or tuning the primary pipeline.

## Reproduction

The worker is `scripts/local_morphnis.py`. Given audited input paths and a fresh output directory, the added flags are:

```sh
--demo-settings --morph-phase --demo-pool-size 100000 --demo-moves de-rwalk \
--nlive 100 --dlogz 0.1 --max-iterations 10000 \
--de-retries 3 --allow-heuristic-recovery
```

`--nismo-repo` selects and verifies the exact implementation. Invocation records retain source hashes, versions, model inputs, seeds and settings. `workflow_settings.json` records resolved defaults. Native results retain all proposal-phase and local-move diagnostics. `comparison.json` separates pilot cost, sampler calls/time and target-validation calls. Wall times from different hardware are not speedup measurements. Additional saved-point replay cost is recorded separately.

Run the immutable plan initially with `scripts/run_sequential_campaign.py --plan PLAN --max-new-events 2`; after inspection, the same plan can resume without the limit. The exclusive controller lock and worker directories prevent duplicate jobs and overwrites. Max-iteration outcomes remain distinct.

Reusable analysis scripts: `scripts/build_main_results.py` (main five metrics, quality alerts, isolated plot namespaces), `scripts/audit_saved_nis.py` (full positive-weight replay), `scripts/validate_demo_controls.py` (descriptive held-out comparisons), `scripts/plot_demo_pairs.py` (focused weighted 2D overlays). Website snapshots are never used as training inputs.

[Public validation receipts and settings](results/mehdi_demo_20261106/) · [Original recovery audit](RECOVERY_DEBUG_20261106.md).
