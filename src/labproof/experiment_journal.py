"""Append-only checkpoints for interrupted fixed-plan experiments.

An unfinished journal is diagnostic evidence, never a completed run or permission
to resume execution. Completed runs bind and validate the journal in their seal.
"""
import os

from .contracts import canonical, require


def append_checkpoint(path, kind, data):
    raw = canonical({"kind": kind, "data": data})
    require(len(raw) <= 500_000, "Oversized experiment checkpoint")
    with path.open("ab") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def expected_checkpoints(run_id, config, acceptance, attempts, executions, status):
    rows = [{"kind": "started", "data": {"run_id": run_id, "plan": config["plan"]}}]
    if config["provisioning"] is not None:
        rows.append({"kind": "provisioned", "data": config})
    if acceptance["accepted"]:
        rows.append({"kind": "accepted", "data": acceptance})
    for index, attempt in enumerate(attempts):
        rows.append({"kind": "attempted", "data": {"step_id": attempt["step_id"], "execution_id": None}})
        if index < len(executions):
            rows.append({"kind": "returned", "data": executions[index]})
    rows.append({"kind": "finished", "data": {"status": status}})
    return rows
