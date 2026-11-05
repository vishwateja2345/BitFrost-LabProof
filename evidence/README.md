# Retained evidence

Real LabProof runs made with Docker Engine in a Debian WSL distribution, plus the image provisioning record. Every run directory re-verifies offline:

```bash
python -m labproof verify-artifacts evidence/local-python-01
```

What each directory is, and the failed attempts that were kept on purpose, is described in [../docs/EVIDENCE.md](../docs/EVIDENCE.md). Hashes are unsigned: they show consistency, not authenticity.
