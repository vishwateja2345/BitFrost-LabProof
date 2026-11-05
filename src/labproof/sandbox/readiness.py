"""Readiness is not a worker assertion or digest equality.

There is no accepted runtime/canary evidence verifier in this foundation. These
checks report missing prerequisites and stale bindings, and ALWAYS stay blocked.
No endpoint probing or process execution occurs when inspecting readiness.
"""
from dataclasses import dataclass

from ..packs import ExecutionAcceptance, PackManifest
from .policy import DOCKER_ENDPOINT, SandboxLimits, policy_fingerprint


@dataclass(frozen=True)
class ReadinessStatus:
    state: str
    reasons: tuple[str, ...]
    endpoint: str = DOCKER_ENDPOINT
    runtime_checked: bool = False
    containment_verified: bool = False

    @property
    def ready(self) -> bool:
        # No public record, including a hand-constructed record, grants authority.
        return False

    def to_dict(self) -> dict:
        return {"state": "blocked", "ready": False, "reasons": list(self.reasons),
                "endpoint": self.endpoint, "runtime_checked": self.runtime_checked,
                "containment_verified": False}


class ReadinessGate:
    """Pure, non-authorizing comparison; only trusted host code supplies context."""

    def inspect(self, *, pack: PackManifest | None = None,
                acceptance: ExecutionAcceptance | None = None,
                runtime_id: str | None = None, plan=None,
                limits: SandboxLimits = SandboxLimits()) -> ReadinessStatus:
        reasons = ["runtime_not_independently_checked",
                   "containment_canary_verifier_not_implemented",
                   "owned_container_lifecycle_not_implemented"]
        if pack is None or not pack.provisioned:
            reasons.append("pack_unprovisioned")
        if plan is None:
            reasons.append("reviewed_launch_adapter_not_provisioned")
        if acceptance is None:
            reasons.append("independent_acceptance_missing")
        elif type(acceptance) is not ExecutionAcceptance:
            reasons.append("worker_assertion_is_not_acceptance")
        else:
            if pack is None or (acceptance.pack_digest, acceptance.image_digest) != (pack.digest, pack.image_digest):
                reasons.append("pack_or_image_acceptance_mismatch")
            if runtime_id is None or runtime_id != acceptance.runtime_id:
                reasons.append("runtime_acceptance_mismatch")
            if plan is None or acceptance.policy_digest != policy_fingerprint(plan, limits):
                reasons.append("policy_acceptance_mismatch")
            reasons.append("canary_evidence_not_independently_authenticated")
        return ReadinessStatus("blocked", tuple(reasons))
