/* Container-only worker; arguments are catalogue enums, never paths/flags. */
#include <stdio.h>
#include <string.h>
#include "response.h"
#define read_record read_alpha
#include "alpha/authz.c"
#undef read_record
#define read_record read_beta
#include "beta/authz.c"
#undef read_record
#define read_record read_gamma
#include "gamma/authz.c"
#undef read_record
#define read_record read_delta
#include "delta/authz.c"
#undef read_record

typedef Response (*Reader)(const char *, const char *);
struct Case { const char *id; const char *actor; const char *record; };
static const struct Case cases[] = {
    {"case-01", "alice", "record-bob"},
    {"case-02", "bob", "record-bob"},
    {"case-03", "alice", "record-alice"},
    {"case-04", "guest", "record-bob"},
    {"case-05", "alice", "record-missing"}
};

int main(int argc, char **argv) {
    static const char *variants[] = {"alpha", "beta", "gamma", "delta"};
    static const Reader readers[] = {read_alpha, read_beta, read_gamma, read_delta};
    size_t chosen = 4;
    if (argc == 3 && strcmp(argv[1], "c-gcc") == 0) {
        for (size_t i = 0; i < 4; ++i) {
            if (strcmp(argv[2], variants[i]) == 0) chosen = i;
        }
    }
    if (chosen == 4) {
        puts("{\"schema_version\":\"worker-observation-1\",\"status\":\"invalid-request\"}");
        return 2;
    }
    Response responses[5];
    for (size_t i = 0; i < 5; ++i) {
        responses[i] = readers[chosen](cases[i].actor, cases[i].record);
        if (responses[i].status < 100 || responses[i].status > 599 || responses[i].body == NULL) {
            /* Fixed source responses only; failures do not disclose environment. */
            puts("{\"schema_version\":\"worker-observation-1\",\"status\":\"invalid-request\"}");
            return 1;
        }
    }
    printf("{\"schema_version\":\"worker-observation-1\",\"operation_id\":\"c-gcc\","
           "\"variant\":\"%s\",\"tool\":\"gcc\",\"tool_version\":\"%d.%d.%d\","
           "\"status\":\"completed\",\"exit_code\":0,\"timed_out\":false,"
           "\"truncated\":false,\"observations\":[", variants[chosen],
           __GNUC__, __GNUC_MINOR__, __GNUC_PATCHLEVEL__);
    for (size_t i = 0; i < 5; ++i) {
        printf("%s{\"case_id\":\"%s\",\"response\":{\"status\":%d,\"body\":%s}}",
               i ? "," : "", cases[i].id, responses[i].status, responses[i].body);
    }
    puts("]}");
    return 0;
}
