// Purpose-built synthetic service; no I/O or external targets.
type Actor = "alice" | "bob";
type RecordData = { id: string; owner: Actor; value: string };
export type Response = { status: number; body: Record<string, string> };
const records = new Map<string, RecordData>([
  ["record-alice", {id: "record-alice", owner: "alice", value: "SYNTHETIC-ALICE"}],
  ["record-bob", {id: "record-bob", owner: "bob", value: "SYNTHETIC-BOB"}],
]);
export function readRecord(actor: string, recordId: string): Response {
  if (actor !== "alice" && actor !== "bob") return {status: 401, body: {error: "unauthorized"}};
  const record = records.get(recordId);
  if (!record) return {status: 404, body: {error: "not_found"}};
  return {status: 200, body: {...record}};
}
