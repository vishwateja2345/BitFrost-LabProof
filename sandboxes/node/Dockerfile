# NON-EXECUTED recipe. Trusted provisioning must supply and approve BASE_IMAGE.
# Context: labproof/. Native Node 24+ erasable TypeScript, NOT the tsc tool.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG BASE_IMAGE
RUN /usr/local/bin/node -e 'if (!/^[a-z0-9][a-z0-9./:_-]*@sha256:[a-f0-9]{64}$/.test(process.argv[1]) || Number(process.versions.node.split(".")[0]) < 24) process.exit(1)' "${BASE_IMAGE}"
COPY sandboxes/node/worker.mjs /worker/worker.mjs
COPY sandboxes/node/observe.test.mjs /worker/observe.test.mjs
COPY src/labproof/fixtures/packs/typescript/alpha/ /fixture/alpha/
COPY src/labproof/fixtures/packs/typescript/beta/ /fixture/beta/
COPY src/labproof/fixtures/packs/typescript/gamma/ /fixture/gamma/
COPY src/labproof/fixtures/packs/typescript/delta/ /fixture/delta/
USER 65532:65532
WORKDIR /tmp
ENTRYPOINT ["/usr/local/bin/node", "/worker/worker.mjs"]
# No default operation. Runtime containment/reset/resource gates remain mandatory.
