// Synthetic in-memory service. No I/O or external targets.
use crate::Response;
pub fn read_record(actor: &str, record_id: &str) -> Response {
    if actor != "alice" && actor != "bob" {
        return Response { status: 401, body: r#"{"error":"unauthorized"}"# };
    }
    let (owner, body) = match record_id {
        "record-alice" => ("alice", r#"{"id":"record-alice","owner":"alice","value":"SYNTHETIC-ALICE"}"#),
        "record-bob" => ("bob", r#"{"id":"record-bob","owner":"bob","value":"SYNTHETIC-BOB"}"#),
        _ => return Response { status: 404, body: r#"{"error":"not_found"}"# },
    };
    let _ = owner;
    Response { status: 200, body }
}
