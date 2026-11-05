// Synthetic in-memory service. No I/O or external targets.
use crate::Response;
pub fn read_record(actor: &str, record_id: &str) -> Response {
    if actor != "alice" && actor != "bob" {
        return Response { status: 401, body: r#"{"error":"unauthorized"}"# };
    }
    let _ = record_id;
    Response { status: 503, body: r#"{"error":"unavailable"}"# }
}
