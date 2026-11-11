# Check an AI answer for stale claims

Bifrost runs the model that selects potentially time-sensitive sentences. LabProof also selects explicitly dated sentences and checks up to three claims. Tavily searches the supplied publisher domains. Bifrost evaluates each claim against the returned excerpts. For claims with one month and year, Bifrost selects the publisher date and LabProof checks that the date appears in the selected excerpt before comparing dates. The HTML and JSON reports retain the claim, score, source excerpts, and selected citation.

Use Python 3.12 or later and a Bifrost gateway with an enabled model and Tavily relay. Set `BIFROST_VIRTUAL_KEY` in the shell. For direct Tavily Search, set `TAVILY_API_KEY` and replace `--search-relay tavily` with `--tavily-key-env TAVILY_API_KEY`. [Local gateway setup](BRIEF.md)

```bash
export PYTHONPATH="$PWD/src"
mkdir -p runs
printf '%s\n' 'Python 3.13 reaches end of life in October 2027.' \
  'Python 3.14 reaches end of life in October 2030.' > runs/python-answer.txt

python -m labproof freshness runs/python-answer.txt \
  --domain devguide.python.org --domain peps.python.org \
  --output runs/python-freshness \
  --gateway-url http://127.0.0.1:8080 --model ollama/qwen2.5:3b \
  --gateway-token-env BIFROST_VIRTUAL_KEY --search-relay tavily \
  --gateway-timeout 145 --confirm-outbound
```

The answer goes to Bifrost and selected search terms go to Tavily. Use public text. Open `freshness.html` for review or use `freshness.json` in a downstream tool. The sample includes one intentionally incorrect date. [Official Python version table](https://devguide.python.org/versions/)

| Evidence | Score |
| --- | ---: |
| Support with a reported publication date within 180 days | 100 |
| Support without a usable publication date | 60 |
| Support with an older publication date | 35 |
| Conflict with the selected source | 0 |
| Insufficient evidence | Unscored |

Review the linked excerpt to see whether the selected date refers to the claimed event. When an individual claim fails search or evaluation, the report preserves the error and any sources already retrieved. The command exits with status 2 for a partial report.

[Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search) · [Bifrost virtual keys](https://docs.getbifrost.ai/features/governance/virtual-keys)


## 90-second judging walkthrough

[Download the Problem 06 pitch deck](pitch/LabProof-Problem-06.pptx).

- **0–20 seconds.** Show the two Python claims and the official support table. Explain how an AI answer can get one support deadline wrong while the rest looks plausible.
- **20–50 seconds.** Open the HTML result. Compare the incorrect 3.13 deadline with its selected source, then show the supported 3.14 deadline and how an undated excerpt affects the score.
- **50–75 seconds.** Explain the provider split. Bifrost serves the model for claim selection and evidence interpretation. Tavily retrieves publisher excerpts. LabProof checks cited dates and calculates the scores.
- **75–90 seconds.** Open the JSON result and show the original claims, retrieved sources, scores, and date selected from each source. Explain what happens when evidence is insufficient.

Use the supplied Tavily Problem 06 brief to select the theme in HackCulture. The organizer requires a public repository and a pitch deck. The source and this walkthrough can support a Problem 06 submission once repository visibility and the final form are settled. [Organizer event page](https://www.geekroom.co.in/event/global-ai-hackathon) · [HackCulture submission dashboard](https://hackculture.io/hackathons/ai-global-hackathon)
