# NON-EXECUTED recipe. Trusted provisioning must supply and approve BASE_IMAGE.
# Context: labproof/. Never use COPY . or copy host oracle/provisioning records.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG BASE_IMAGE
RUN /usr/local/bin/python -I -c 'import re,sys; sys.exit(0 if re.fullmatch(r"[a-z0-9][a-z0-9./:_-]*@sha256:[a-f0-9]{64}",sys.argv[1]) and sys.version_info >= (3,12) else 1)' "${BASE_IMAGE}"
COPY sandboxes/python/worker.py /worker/worker.py
COPY src/labproof/fixtures/packs/python/alpha/ /fixture/alpha/
COPY src/labproof/fixtures/packs/python/beta/ /fixture/beta/
COPY src/labproof/fixtures/packs/python/gamma/ /fixture/gamma/
COPY src/labproof/fixtures/packs/python/delta/ /fixture/delta/
USER 65532:65532
WORKDIR /tmp
ENV PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["/usr/local/bin/python", "-I", "-B", "/worker/worker.py"]
# No default operation. Runtime containment/reset/resource gates remain mandatory.
