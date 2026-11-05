/* Synthetic in-memory service. No I/O or external targets. */
static Response read_record(const char *actor, const char *record_id) {
    if (strcmp(actor, "alice") != 0 && strcmp(actor, "bob") != 0)
        return (Response){401, "{\"error\":\"unauthorized\"}"};
    const char *owner;
    const char *body;
    if (strcmp(record_id, "record-alice") == 0) {
        owner = "alice";
        body = "{\"id\":\"record-alice\",\"owner\":\"alice\",\"value\":\"SYNTHETIC-ALICE\"}";
    } else if (strcmp(record_id, "record-bob") == 0) {
        owner = "bob";
        body = "{\"id\":\"record-bob\",\"owner\":\"bob\",\"value\":\"SYNTHETIC-BOB\"}";
    } else {
        return (Response){404, "{\"error\":\"not_found\"}"};
    }
    (void)owner;
    return (Response){200, body};
}
