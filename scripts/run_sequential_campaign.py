#!/usr/bin/env python3
"""Execute an immutable local NIS job plan, one child process at a time.

Exclusive controller locking and exclusive worker output directories prevent
duplicate jobs. Completed outcomes are reused on restart; incomplete existing
directories halt for inspection. Create STOP_AFTER_CURRENT to stop gracefully.
"""
from __future__ import annotations

import argparse
import csv
import fcntl
import hashlib
import io
import json
import os
import signal
import statistics
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def new_json(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def derived(path, value):
    """Only replace live summaries, never sampling outputs or event receipts."""
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w") as stream:
        stream.write(value if isinstance(value, str) else json.dumps(value, indent=2, allow_nan=False)+"\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def fingerprint(job):
    return hashlib.sha256(json.dumps(job, sort_keys=True).encode()).hexdigest()


def acquire_lock(path):
    stream = Path(path).open("a+")
    try:
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        stream.close()
        raise RuntimeError("Another controller already holds this campaign lock") from None
    stream.seek(0)
    stream.truncate()
    stream.write(json.dumps({"pid": os.getpid(), "started_utc": now()}))
    stream.flush()
    return stream


def classify(directory, event, returncode):
    directory = Path(directory)
    comparison = directory / "comparison.json"
    if comparison.exists() and (directory / "nis/result.npz").exists():
        data = read(comparison)
        if data["event"] != event:
            raise ValueError("Saved output belongs to another event")
        reason = data["termination_reason"]
        expected = "converged" if reason in ("dlogz", "flat_log_psi") else "non_converged"
        if reason not in ("dlogz", "flat_log_psi", "max_iterations") or data["status"] != expected:
            raise ValueError("Unknown/inconsistent sampler termination")
        if returncode not in (0, 3, None):
            raise RuntimeError(f"Worker exited {returncode} after saving a comparison; inspect output")
        return {"event": event, "status": expected, "termination_reason": reason,
            "output": str(directory), "returncode": returncode,
            "nis": data["nis"], "data_origin": data.get("data_origin", {"kind": "original_frozen"}),
            "delta_logz_nis_reference": data["delta_logz_nis_reference"],
            "delta_logz_nis_reference_statistical_error": data["delta_logz_nis_reference_statistical_error"],
            "delta_logz_cheap_reference": data["delta_logz_cheap_reference"],
            "cost_including_pilot": data["cost_including_pilot"],
            "result_sha256": sha(directory / "nis/result.npz"),
            "comparison_sha256": sha(comparison),
            "plot_failed": (directory / "plot_failure.json").exists()}
    if (directory / "failure.json").exists():
        failure = read(directory / "failure.json")
        if failure.get("phase") == "sampling" and failure["error_type"] == "ConstrainedSamplingError":
            return {"event": event, "status": "failed", "output": str(directory),
                "returncode": returncode, "error_type": failure["error_type"], "error": failure["error"],
                "likelihood_calls": failure.get("likelihood_calls"), "seconds": failure["seconds"],
                "failure_sha256": sha(directory / "failure.json"),
                "failed_walk_attempts": sum(not row["succeeded"] for row in failure.get("recovery_history", []))}
        raise RuntimeError(f"Worker blocked in {failure.get('phase')}: {failure['error_type']}: {failure['error']}")
    raise RuntimeError(f"Worker exited {returncode} without an authoritative result: {directory}")


def publish(root, plan, outcomes, state, active=None, error=None):
    counts = dict(Counter(row["status"] for row in outcomes))
    status = {"state": state, "controller_pid": os.getpid(), "updated_utc": now(),
        "total_events": len(plan["jobs"]), "finished_events": len(outcomes),
        "remaining_events": len(plan["jobs"])-len(outcomes), "outcome_counts": counts,
        "active": active, "error": error,
        "interpretation": "Stopping-threshold outcomes are provisional; inspect recovery, mixing and reference differences."}
    successful = [row for row in outcomes if row["status"] == "converged"]
    if successful:
        status["converged_summary"] = {
            "median_delta_logz_nis_reference": statistics.median(row["delta_logz_nis_reference"] for row in successful),
            "median_weight_ess": statistics.median(row["nis"]["weight_ess"] for row in successful),
            "recovery_iterations": sum(row["nis"]["recovery_iterations"] for row in successful)}
    derived(root / "status.json", status)
    columns = ["event", "status", "reused", "data_origin", "log_evidence", "log_evidence_err",
        "delta_logz_nis_reference", "delta_statistical_error", "weight_ess", "iterations",
        "recovery_iterations", "likelihood_calls", "pilot_likelihood_calls", "sampler_seconds", "output"]
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=columns)
    writer.writeheader()
    markdown = ["# Sequential local NIS campaign", "", f"State: **{state}**. Finished {len(outcomes)}/{len(plan['jobs'])} events.",
        "", "One local worker at a time. Data origin and failures are explicit. Stopping thresholds and weight ESS do not establish unbiased sampling.",
        "", "| Event | Outcome | logZ ± reported error | Weight ESS | Recovery iterations |", "| --- | --- | --- | ---: | ---: |"]
    for row in outcomes:
        nis = row.get("nis", {})
        cost = row.get("cost_including_pilot", {})
        pilot = next(job["pilot_likelihood_calls"] for job in plan["jobs"] if job["event"] == row["event"])
        writer.writerow({"event": row["event"], "status": row["status"], "reused": row.get("reused", False),
            "data_origin": row.get("data_origin", {}).get("kind", "validated_reconstruction"),
            "log_evidence": nis.get("log_evidence"), "log_evidence_err": nis.get("log_evidence_err"),
            "delta_logz_nis_reference": row.get("delta_logz_nis_reference"),
            "delta_statistical_error": row.get("delta_logz_nis_reference_statistical_error"),
            "weight_ess": nis.get("weight_ess"), "iterations": nis.get("n_iterations"),
            "recovery_iterations": nis.get("recovery_iterations"),
            "likelihood_calls": nis.get("likelihood_calls", row.get("likelihood_calls")),
            "pilot_likelihood_calls": pilot, "sampler_seconds": nis.get("sampler_seconds", row.get("seconds")),
            "output": row["output"]})
        estimate = f"{nis['log_evidence']:.4f} ± {nis['log_evidence_err']:.4f}" if nis else "unavailable"
        markdown.append(f"| {row['event']:03d} | {row['status']}{' (reused)' if row.get('reused') else ''} | {estimate} | {nis.get('weight_ess', '')} | {nis.get('recovery_iterations', '')} |")
    if active:
        markdown += ["", f"Running event **{active['event']:03d}**, elapsed {active['elapsed_seconds']:.0f} s."]
    if error:
        markdown += ["", f"Stopped for inspection: {error}"]
    markdown += ["", "The summary CSV includes the cheap pilot separately. Comparison JSONs retain posterior distances and per-event statistical errors; corner overlays are in each event output.",
        "", "Create `STOP_AFTER_CURRENT` in this campaign directory for a graceful stop. Previous event files are never overwritten."]
    derived(root / "summary.csv", stream.getvalue())
    derived(root / "summary.md", "\n".join(markdown)+"\n")


def run_plan(plan_path):
    plan = read(plan_path)
    root = Path(plan["campaign_root"])
    root.mkdir(parents=True, exist_ok=True)
    lock = acquire_lock(root / "controller.lock")
    outcomes = []
    stop = [False]
    previous_handlers = {sig: signal.signal(sig, lambda *_: stop.__setitem__(0, True))
                         for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        plan_receipt = root / "plan_checksum.json"
        if plan_receipt.exists():
            if read(plan_receipt)["sha256"] != sha(plan_path):
                raise ValueError("Campaign plan changed; use a fresh campaign directory")
        else:
            new_json(plan_receipt, {"sha256": sha(plan_path)})
        for item in plan.get("pinned_files", []):
            if sha(item["path"]) != item["sha256"]:
                raise ValueError(f"Pinned input/code changed: {item['path']}")
        (root / "outcomes").mkdir(exist_ok=True)
        (root / "logs").mkdir(exist_ok=True)
        publish(root, plan, outcomes, "running")
        for job in plan["jobs"]:
            event = job["event"]
            receipt = root / "outcomes" / f"event_{event:03d}.json"
            if receipt.exists():
                outcome = read(receipt)
                if outcome["job_fingerprint"] != fingerprint(job):
                    raise ValueError(f"Existing event receipt belongs to a different job: {event}")
                for filename, key in (("nis/result.npz", "result_sha256"),
                                      ("comparison.json", "comparison_sha256"),
                                      ("failure.json", "failure_sha256")):
                    if key in outcome and sha(Path(outcome["output"]) / filename) != outcome[key]:
                        raise ValueError(f"Existing event output changed: {event}/{filename}")
                outcomes.append(outcome)
                continue
            if stop[0] or (root / "STOP_AFTER_CURRENT").exists():
                publish(root, plan, outcomes, "stopped_after_current")
                return 0
            for item in job.get("pinned_files", []):
                if sha(item["path"]) != item["sha256"]:
                    raise ValueError(f"Event {event} input changed: {item['path']}")
            if job.get("reuse"):
                if sha(Path(job["reuse"]) / "nis/result.npz") != job["reuse_result_sha256"]:
                    raise ValueError("Reused event result changed")
                outcome = classify(job["reuse"], event, None)
                outcome["reused"] = True
            else:
                directory = Path(job["output"])
                if directory.exists():
                    # Never retry or adopt an ambiguous worker automatically.
                    raise FileExistsError(f"Existing worker output needs inspection; not launching a duplicate: {directory}")
                for item in plan.get("pinned_files", []):
                    if sha(item["path"]) != item["sha256"]:
                        raise ValueError(f"Pinned input/code changed: {item['path']}")
                start = time.monotonic()
                log_path = root / "logs" / f"event_{event:03d}.log"
                with log_path.open("x") as log:
                    process = subprocess.Popen(job["command"], stdout=log, stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL, start_new_session=True,
                        env={**os.environ, "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1",
                             "MKL_NUM_THREADS": "1", "VECLIB_MAXIMUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1"})
                    while process.poll() is None:
                        active = {"event": event, "worker_pid": process.pid, "log": str(log_path),
                                  "elapsed_seconds": time.monotonic()-start, "output": str(directory)}
                        publish(root, plan, outcomes, "running", active)
                        time.sleep(5)
                outcome = classify(directory, event, process.returncode)
                outcome["reused"] = False
                outcome["invocation_seconds"] = time.monotonic()-start
            outcome.update(job_fingerprint=fingerprint(job), recorded_utc=now(),
                           pilot_likelihood_calls=job["pilot_likelihood_calls"])
            new_json(receipt, outcome)
            outcomes.append(outcome)
            publish(root, plan, outcomes, "running")
            print(json.dumps({"event": event, "status": outcome["status"], "reused": outcome["reused"]}), flush=True)
        publish(root, plan, outcomes, "completed")
        return 0
    except Exception as error:
        publish(root, plan, outcomes, "blocked", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
        lock.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    raise SystemExit(run_plan(parser.parse_args().plan))
