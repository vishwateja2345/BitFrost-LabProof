/* Synthetic in-memory service. No I/O or external targets. */
static Response read_record(const char *actor, const char *record_id) {
    if (strcmp(actor, "alice") != 0 && strcmp(actor, "bob") != 0)
        return (Response){401, "{\"error\":\"unauthorized\"}"};
    (void)record_id;
    return (Response){503, "{\"error\":\"unavailable\"}"};
}
