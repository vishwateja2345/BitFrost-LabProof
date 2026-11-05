"""Evidence registration with immutable content-addressed records."""
from hashlib import sha256
from pathlib import Path

from .contracts import canonical, require
from .policy import Action
from .transport import Response


def record_evidence(root: Path, action: Action, response: Response, variant: str, phase: str, fixture_sha: str) -> dict:
    payload = {
        "check_id": action.check_id.value, "actor_id": action.actor_id,
        "variant": variant, "control": action.control, "phase": phase,
        "response": response.to_dict(), "source": "synthetic_fixture",
        "fixture_sha256": fixture_sha,
    }
    raw = canonical(payload)
    digest = sha256(raw).hexdigest()
    evidence_id = "ev_" + digest[:24]
    relative = f"evidence/{evidence_id}.json"
    target = root / relative
    target.parent.mkdir(exist_ok=True)
    require(not target.exists(), "Duplicate evidence record")
    with target.open("xb") as stream:
        stream.write(raw)
    return {
        "id": evidence_id, "title": f"{action.check_id.value}: {variant} / {action.control} / {phase}",
        "content": response.body, "artifact_path": relative, "sha256": digest,
        **payload,
    }
