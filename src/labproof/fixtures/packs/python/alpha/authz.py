"""Purpose-built synthetic record service; no I/O or external targets."""
RECORDS = {
    "record-alice": {"id": "record-alice", "owner": "alice", "value": "SYNTHETIC-ALICE"},
    "record-bob": {"id": "record-bob", "owner": "bob", "value": "SYNTHETIC-BOB"},
}


def read_record(actor, record_id):
    if actor not in ("alice", "bob"):
        return {"status": 401, "body": {"error": "unauthorized"}}
    record = RECORDS.get(record_id)
    if record is None:
        return {"status": 404, "body": {"error": "not_found"}}
    return {"status": 200, "body": dict(record)}
