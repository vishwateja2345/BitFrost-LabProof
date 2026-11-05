"""Explicit runtime acceptance for installed fixed-v2 profiles, not offline CI.

Requires the existing authorized Debian Docker controller and reviewed candidate
provisioning. Writes only a new output directory; never installs provisioning or
changes Docker/Windows security. Synthetic allowlisted fixtures only.
"""
import argparse
from hashlib import sha256
from pathlib import Path
import sys

from labproof.contracts import canonical, check_no_links, read_safe, require, parse_json
from labproof.engine import write_new
from labproof.local_engine import run_experiments, provisioned_experiment
from labproof.local_profiles import default_experiment_plan, validate_experiment_plan, VARIANTS
from labproof.verify_artifacts import verify_artifacts


def full_plan(pack):
    plan = default_experiment_plan(pack)
    request = {**plan["steps"][0]["request"], "parameters": {"variant": "delta"}}
    plan["steps"].extend([
        {"id": "observe_delta", "request": request, "phase": "observation", "replay_of": None},
        {"id": "replay_delta", "request": request, "phase": "verification", "replay_of": "observe_delta"}])
    profile = validate_experiment_plan(plan)
    plan["budgets"] = {"actions": 8,
                       "wall_seconds": int(8 * (profile.local.limits.wall_seconds + profile.local.limits.cleanup_seconds)),
                       "output_bytes": 8 * profile.local.limits.output_bytes}
    validate_experiment_plan(plan)
    return plan


def accept(output, packs):
    import labproof
    package = Path(labproof.__file__).parent
    require("site-packages" in package.parts or "dist-packages" in package.parts,
            "Runtime acceptance requires installed package identity")
    require(sys.flags.isolated and sys.flags.optimize, "Use isolated optimized Python (-I -O)")
    output = Path(output).absolute()
    check_no_links(output.parent)
    output.mkdir()
    result = {"schema_version": "fixed-v2-runtime-acceptance-1", "status": "incomplete",
              "python": sys.version, "installed_package": str(package), "packs": [],
              "limitations": ["Synthetic fixed authorization fixtures, not new property/sanitizer acceptance.",
                              "Containment evidence covers tested controls, not container escape immunity."]}
    try:
        for pack in packs:
            plan = full_plan(pack)
            provenance = provisioned_experiment(validate_experiment_plan(plan))
            write_new(output / (pack + "-plan.json"), canonical(plan))
            path = output / pack
            manifest = run_experiments(path, plan)
            verified = verify_artifacts(path)
            report = parse_json(read_safe(path, "report.json"))
            row = {"pack_id": pack, "status": manifest["status"], "verification": verified,
                   "provenance_sha256": sha256(canonical(provenance)).hexdigest(),
                   "manifest_sha256": sha256(read_safe(path, "manifest.json")).hexdigest(),
                   "executions": len(report["experiments"]),
                   "findings": {f["variant"]: f["status"] for f in report["findings"]}}
            result["packs"].append(row)
            require(verified["complete"] and row["executions"] == 8, "Runtime execution incomplete")
            require(row["findings"] == {"alpha": "confirmed", "beta": "rejected", "gamma": "rejected", "delta": "inconclusive"},
                    "Runtime controls did not match reviewed fixture behavior")
            print(pack + ": eight fresh executions verified", flush=True)
        result["status"] = "accepted_fixed_v2_only"
    except (Exception, KeyboardInterrupt) as error:
        result["error_type"] = type(error).__name__
        raise
    finally:
        write_new(output / "runtime-acceptance.json", canonical(result))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pack", action="append", choices=["python", "typescript", "c", "rust"], required=True)
    args = parser.parse_args()
    require(len(args.pack) == len(set(args.pack)), "Duplicate acceptance pack")
    accept(args.output, args.pack)


if __name__ == "__main__":
    main()
