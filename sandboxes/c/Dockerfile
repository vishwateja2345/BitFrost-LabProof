# Provisioning only. Parent supplies an approved digest-pinned official GCC image.
# Build context is labproof/. Compiler diagnostics are emitted during image build;
# the runtime operation observes the compiled fixture, not a new scanner run.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG BASE_IMAGE
RUN printf '%s\n' "$BASE_IMAGE" | grep -Eq '^(gcc|docker.io/library/gcc)(:[a-zA-Z0-9._-]+)?@sha256:[a-f0-9]{64}$'
# Fixed native containment-canary prerequisites; fail build, never auto-install.
RUN test -x /bin/sh && for tool in id awk cat stat env od tr cp chmod head sleep true; do test -x "/usr/bin/$tool" || exit 1; done
COPY sandboxes/c/worker.c sandboxes/c/response.h /worker/
COPY src/labproof/fixtures/packs/c/alpha/authz.c /fixture/alpha/authz.c
COPY src/labproof/fixtures/packs/c/beta/authz.c /fixture/beta/authz.c
COPY src/labproof/fixtures/packs/c/gamma/authz.c /fixture/gamma/authz.c
COPY src/labproof/fixtures/packs/c/delta/authz.c /fixture/delta/authz.c
RUN gcc -std=c17 -O2 -Wall -Wextra -Wpedantic -Werror -I/fixture /worker/worker.c -o /worker/observe
USER 65532:65532
WORKDIR /tmp
ENTRYPOINT ["/worker/observe"]
# Fixed runtime arguments: c-gcc alpha|beta|gamma|delta. No default operation.
