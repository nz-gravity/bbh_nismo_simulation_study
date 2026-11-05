# Sequential local campaign — 5 November 2026

The user authorized running the 100 NIS events locally, **one at a time**.
This campaign uses the fixed primary configuration from the successful smoke
tests and explicitly audited reconstructions. Results remain experimental:
recovery and correlated replacements may affect posteriors and evidence errors.
The recovery-free probe's failure is retained in the earlier study record.

Each new event uses NIS `nlive=100`, `dlogz=0.1`, maximum 10,000 iterations,
DE/stretch weights 0.8/0.2, adaptive DE, the default 125-step initial walk and
up to 3 recorded heuristic retries. Fit seed is `20261104 + event_id`; sampling
seed is `20262104 + event_id`. All cheap posterior rows train the proposal,
with `thin=1`. Reference samples validate the target and support comparison;
they never train or tune the proposal.

Event 0's original-data primary result has exactly these settings and is reused
after checking its invocation, training metadata, likelihood identity and hashes.
Events 1–99 use the separately labelled reconstructed data. Each must have the
matching full-cheap/32-reference reconstruction audit and pass fresh density
replays before sampling. Original and reconstructed target identities and
checksums are both retained in each comparison JSON.

The two completed event-0 NIS samplers took 234.6 and 291.6 seconds, plus fitting
and setup. This suggests roughly 7–9 hours for the remaining 99 serial jobs if
their costs are similar. This is an estimate from one event, not a runtime cap
or a claim about all injections. Individual difficult events can take longer.

## Execution and outputs

The saved campaign plan lists all 100 events, exact commands, input hashes,
source hashes, settings and the single reused result. A snapshot of the worker,
controller and release manifest is copied into its `code/` directory. The
controller runs with that plan and one child at a time; numerical library
thread counts are set to one. macOS `caffeinate -is` prevents idle sleep while
the controller runs. This is a local process campaign, not an OzSTAR submission.

- `status.json`: live state, worker PID, current event, elapsed time and counts.
- `summary.md` / `summary.csv`: updated after each job and during monitoring.
- `outcomes/event_NNN.json`: immutable authoritative event receipt.
- `events/event_NNN/attempt_001/`: invocation, validation, weighted NPZ, traces,
  evidence/posterior comparison and corner plot for each new job.
- `logs/event_NNN.log`: each worker's output; `controller.log` records dispatch.

The controller exclusively locks its campaign directory. Each worker exclusively
creates its output directory. A second controller is refused; completed matching
receipts are skipped on restart. Changed plans, source files, inputs or previous
results stop execution. Ambiguous pre-existing worker output also stops for
inspection, rather than launching another job. Original inputs, smoke outputs
and published baseline results are never overwritten. Only the live summaries
are intentionally replaced.

A sampling `ConstrainedSamplingError` is saved as failed and the next event runs.
Reaching the iteration cap is saved as non-converged, exit code 3, and remains
separate from failure and convergence. Validation, fitting, export or unknown
runtime errors halt the queue. A plot failure does not relabel a completed
sampler outcome.

Create a file named `STOP_AFTER_CURRENT` in the campaign directory to stop
gracefully after the active event. For a restart, remove that marker and use
the unchanged saved plan:

```sh
PINNED_PYTHON CAMPAIGN/code/scripts/run_sequential_campaign.py --plan CAMPAIGN/plan.json
```

`summary.csv` keeps the cheap pilot's likelihood-call count separate, so its
cost can be included once per event. Earlier repeat/strict smoke tests are
additional diagnostic costs, not additional primary results. The final
comparison should distinguish numerical stopping, weight ESS and statistical
errors from mixing, proposal coverage and possible recovery bias.
