# Live citation check

LabProof ran the fixed authorization remediation query against Tavily and sent the returned public passages to Ollama `qwen2.5:3b` through Bifrost `v2.4.0`. The input was the retained Python container record in [local-python-01](../local-python-01). Both direct Tavily search and search through the Bifrost relay returned one recommendation with a verified quotation. Both briefs passed offline verification against the same run. The JSON records include provider routes, token usage, citations, and the saved excerpts.

```bash
python -m labproof verify-brief evidence/local-python-01 evidence/live-brief-03/direct
python -m labproof verify-brief evidence/local-python-01 evidence/live-brief-03/relay
```
