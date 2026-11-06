"""Exercise sequencing, restart safety and stop policy using tiny fake workers."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts/run_sequential_campaign.py"
spec = importlib.util.spec_from_file_location("sequential_campaign", SCRIPT)
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)


@pytest.fixture
def make_plan(tmp_path):
    worker = tmp_path / "fake_worker.py"
    worker.write_text('''import json,sys,time
from pathlib import Path
event=int(sys.argv[1]); output=Path(sys.argv[2]); journal=Path(sys.argv[3]); kind=sys.argv[4]
output.mkdir(parents=True)
with journal.open('a') as f:f.write(f'START {event}\\n')
time.sleep(.05)
if kind in ('sampling_failure','validation_failure'):
 data={'phase':'sampling' if kind=='sampling_failure' else 'validation','error_type':'ConstrainedSamplingError' if kind=='sampling_failure' else 'ValueError','error':'test fixture','seconds':.05,'likelihood_calls':2,'recovery_history':[]}
 (output/'failure.json').write_text(json.dumps(data)); code=1
else:
 (output/'nis').mkdir(); (output/'nis/result.npz').write_bytes(b'orchestration fixture, not scientific samples')
 data={'event':event,'status':'non_converged' if kind=='cap' else 'converged','termination_reason':'max_iterations' if kind=='cap' else 'dlogz','nis':{'log_evidence':0.,'log_evidence_err':1.,'weight_ess':2.,'n_iterations':1,'recovery_iterations':0,'likelihood_calls':2,'sampler_seconds':.05},'delta_logz_nis_reference':0.,'delta_logz_nis_reference_statistical_error':1.,'delta_logz_cheap_reference':0.,'cost_including_pilot':{}}
 (output/'comparison.json').write_text(json.dumps(data)); code=3 if kind=='cap' else 0
with journal.open('a') as f:f.write(f'END {event}\\n')
raise SystemExit(code)
''')

    def prepare(kinds):
        root = tmp_path / "campaign"
        root.mkdir()
        journal = tmp_path / "order.txt"
        jobs = []
        for event, kind in enumerate(kinds):
            output = root / "events" / f"event_{event:03d}"
            jobs.append({"event": event, "output": str(output), "pilot_likelihood_calls": 10,
                "command": [sys.executable, str(worker), str(event), str(output), str(journal), kind]})
        plan = tmp_path / "plan.json"
        plan.write_text(json.dumps({"campaign_root": str(root), "pinned_files": [], "jobs": jobs}))
        return plan, root, journal
    return prepare


def test_workers_are_serial_and_restarts_do_not_duplicate(make_plan):
    plan, root, journal = make_plan(["cap", "sampling_failure", "success"])
    assert campaign.run_plan(plan) == 0
    assert journal.read_text().splitlines() == ['START 0', 'END 0', 'START 1', 'END 1', 'START 2', 'END 2']
    status = campaign.read(root / "status.json")
    assert status["outcome_counts"] == {"non_converged": 1, "failed": 1, "converged": 1}
    before = journal.read_bytes()
    assert campaign.run_plan(plan) == 0
    assert journal.read_bytes() == before


def test_scientific_failure_stops_before_next_event(make_plan):
    plan, root, journal = make_plan(["validation_failure", "success"])
    with pytest.raises(RuntimeError, match="blocked in validation"):
        campaign.run_plan(plan)
    assert journal.read_text().splitlines() == ['START 0', 'END 0']
    assert campaign.read(root / "status.json")["state"] == "blocked"
    assert not (root / "events/event_001").exists()


def test_smoke_limit_preserves_plan_and_resume_skips_completed_workers(make_plan):
    plan, root, journal = make_plan(["success", "success", "success"])
    before = plan.read_bytes()
    assert campaign.run_plan(plan, max_new_events=2) == 0
    assert campaign.read(root / "status.json")["state"] == "stopped_after_current"
    assert journal.read_text().splitlines() == ['START 0', 'END 0', 'START 1', 'END 1']
    assert campaign.run_plan(plan) == 0
    assert plan.read_bytes() == before
    assert journal.read_text().splitlines() == ['START 0', 'END 0', 'START 1', 'END 1', 'START 2', 'END 2']


def test_second_controller_cannot_acquire_campaign_lock(tmp_path):
    first = campaign.acquire_lock(tmp_path / "lock")
    try:
        with pytest.raises(RuntimeError, match="Another controller"):
            campaign.acquire_lock(tmp_path / "lock")
    finally:
        first.close()
