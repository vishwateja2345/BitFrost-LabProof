# LabProof demo

Open the viewer from the repository root.

```bash
npm --prefix viewer ci
npm --prefix viewer run dev
```

Visit [the local viewer](http://127.0.0.1:5173/). The saved lab review contains four recorded container runs, 16 findings, and 32 evidence records. The Python run includes a retained live remediation brief. The viewer runs entirely in the browser.

## Two-minute walkthrough

1. Start in **Results**. The first Python finding shows the expected invariant beside the observed result. Select the rejected finding for the corrected variant to compare the outcome.
2. Return to the confirmed Python finding. Open a linked evidence record to see the captured response and execution lineage. Open **Run trace** to show the recorded event order.
3. Select **View cited remediation** from the confirmed finding, or open **Remediation**. Show the saved Tavily search through the Bifrost relay, the model-generated recommendation, and the exact excerpts it cites. Select the linked finding to return to its evidence.
4. Close with the offline CLI verification. It checks the saved run and brief against each other and rechecks the retained quotations.

```bash
python -m labproof verify-artifacts evidence/local-python-01
python -m labproof verify-brief evidence/local-python-01 evidence/live-brief-01/relay
```

## Generate a fresh offline bundle

With Python 3.12 or later available, run this from the repository root.

```bash
scripts/demo-review.sh
```

Import the printed `review.json` path. This produces a fresh synthetic replay and a scripted brief with three recommendations. The four other runs are retained container records. The Remediation tab labels the scripted provider responses and invented citations.

To include an existing brief in your own export, give its completed source run as the first directory.

```bash
python -m labproof export-viewer evidence/local-python-01 \
  --brief evidence/live-brief-01/relay --output runs/python-review.json
```

## Fresh live provider run

Get a Tavily key from the [Tavily dashboard](https://app.tavily.com/). The included gateway script creates its own Bifrost virtual key. It uses a local Ollama model, which needs the model downloaded and running. Docker and Python are also required. Save `TAVILY_API_KEY` in the ignored local `.env` before loading it into the shell. A separately managed gateway uses its own [Bifrost virtual key](https://docs.getbifrost.ai/features/governance/virtual-keys) in `BIFROST_VIRTUAL_KEY`. Hosted model credentials belong in that gateway's provider configuration.

```bash
set -a
. ./.env
set +a
MODES=relay CALL_TIMEOUT=150 scripts/live-brief/run.sh
```

The script sends a fixed public-guidance query to Tavily and public excerpts to the model. See [provider setup and troubleshooting](BRIEF.md) for the direct-search path and failure states. The retained record lets you present the provider workflow offline when credentials or networking are unavailable.

## Hackathon scope

LabProof's demo covers reproducible synthetic findings, evidence review, offline consistency checks, and sourced remediation. The Problem 03 brief also requires autonomous exploration of an organizer-provided unfamiliar target and completion of a lab objective. This demo does not establish those requirements.

Geek Room lists November 15, 2026 as the prototype deadline and November 29 as judging day. Check the signed-in event dashboard for the submission form and its required fields. [Organizer event page](https://www.geekroom.co.in/event/global-ai-hackathon) · [HackCulture event](https://hackculture.io/hackathons/ai-global-hackathon)
