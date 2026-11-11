# Live provider verification on Docker Desktop

These briefs were recorded on November 11, 2026 from the retained [Python container run](../local-python-01). Each route made one live Tavily search and retained three public guidance sources. Verify the records offline with `python -m labproof verify-brief evidence/local-python-01 <brief-directory>`.

| Record | Search route | Gateway outcome | Advice |
| --- | --- | --- | --- |
| [Initial direct](initial/direct) | Tavily API | HTTP 403, model blocked | None |
| [Initial relay](initial/relay) | Tavily through Bifrost | HTTP 403, model blocked | None |
| [Direct](direct) | Tavily API | Ollama `qwen2.5:3b` served the request through Bifrost | Reply did not pass JSON validation |
| [Relay](relay) | Tavily through Bifrost | Ollama `qwen2.5:3b` served the request through Bifrost | Quotation was absent from the retained source |
| [Script relay](script-relay) | Tavily through Bifrost | The updated live script routed to Ollama and verified the saved brief | No recommendation passed the quotation check. The script returned `2` for the partial brief. |

The successful provider connections used `maximhq/bifrost:v2.4.0` and an Ollama container on a dedicated Docker bridge. The gateway was published to loopback, with a virtual key scoped to `qwen2.5:3b`. Ollama used its explicit private provider URL. The gateway was started from temporary configuration with credentials passed through environment variables.

The workspace includes the [earlier sourced relay brief](../live-brief-01/relay). These fresh runs demonstrate the current provider connection and the verifier's handling of model output that fails its checks.
