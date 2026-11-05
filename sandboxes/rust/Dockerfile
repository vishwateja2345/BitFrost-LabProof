# Provisioning only. Parent supplies an approved digest-pinned official Rust image.
# Build context labproof/. No external dependencies, downloads or copied oracle.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG BASE_IMAGE
RUN printf '%s\n' "$BASE_IMAGE" | grep -Eq '^(rust|docker.io/library/rust)(:[a-zA-Z0-9._-]+)?@sha256:[a-f0-9]{64}$'
# Fixed native containment-canary prerequisites; fail build, never auto-install.
RUN test -x /bin/sh && for tool in id awk cat stat env od tr cp chmod head sleep true; do test -x "/usr/bin/$tool" || exit 1; done
COPY sandboxes/rust/Cargo.toml sandboxes/rust/Cargo.lock /worker/
COPY sandboxes/rust/src/main.rs /worker/src/main.rs
COPY src/labproof/fixtures/packs/rust/alpha/authz.rs /fixture/alpha/authz.rs
COPY src/labproof/fixtures/packs/rust/beta/authz.rs /fixture/beta/authz.rs
COPY src/labproof/fixtures/packs/rust/gamma/authz.rs /fixture/gamma/authz.rs
COPY src/labproof/fixtures/packs/rust/delta/authz.rs /fixture/delta/authz.rs
RUN /usr/local/cargo/bin/cargo --version | cut -d ' ' -f 2 > /worker/cargo-version.txt && \
    grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+([a-zA-Z0-9.+-]*)?$' /worker/cargo-version.txt && \
    /usr/local/cargo/bin/cargo build --offline --locked --release --manifest-path /worker/Cargo.toml --target-dir /build-target && \
    cp /build-target/release/labproof-worker /worker/observe && \
    rm -rf /build-target
ENV CARGO_NET_OFFLINE=true
USER 65532:65532
WORKDIR /tmp
ENTRYPOINT ["/worker/observe"]
# rust-cargo-test alpha|beta|gamma|delta. Requires reviewed exec /output policy:
# Cargo compiles/runs tests in /output/cargo-target; /scratch remains noexec.
# No host execution fallback; default all-noexec policy must keep this blocked.
