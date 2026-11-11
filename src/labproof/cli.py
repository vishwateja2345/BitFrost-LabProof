"""Independent command-line entry points; stdout is machine-readable JSON."""
import argparse
import json
import os
from pathlib import Path
import sys

from .contracts import ValidationError, check_no_links, parse_json
from .packs import PackError
from .engine import run_demo
from .policy import Limits, PolicyError
from .transport import doctor
from .verify_artifacts import verify_artifacts


def main(argv=None):
    parser = argparse.ArgumentParser(prog="labproof", description="Synthetic replay and bounded local language experiments. No arbitrary target support.")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Run canned observations offline into a NEW output directory")
    demo.add_argument("--output", type=Path, required=True)
    demo.add_argument("--max-actions", type=int, default=36, help="Lower the replay budget (0-36)")
    verify = commands.add_parser("verify-artifacts", help="Validate saved artifacts without executing checks")
    verify.add_argument("directory", type=Path)
    commands.add_parser("packs", help="List declared language operations; does not execute or probe tools")
    commands.add_parser("doctor", help="Report replay readiness and blocked assessment gates")
    assess = commands.add_parser("assess", help="Run a provisioned synthetic pack only after containment acceptance")
    assess.add_argument("--mode", choices=["local"])
    assess.add_argument("--pack", choices=["python", "typescript", "c", "rust"])
    assess.add_argument("--output", type=Path)
    export = commands.add_parser("export-viewer", help="Verify own runs and exclusively write a viewer bundle up to 5 MiB")
    export.add_argument("directories", type=Path, nargs="+")
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--brief", type=Path, help="Include a verified remediation brief for the first run directory")
    review = commands.add_parser("review-export", help="Require a one-use approval for a defensive viewer export")
    review.add_argument("--ledger", type=Path, required=True, help="Local SQLite approval ledger")
    review_commands = review.add_subparsers(dest="review_command", required=True)
    approve = review_commands.add_parser("approve", help="Sign an approval for one local export")
    redeem = review_commands.add_parser("redeem", help="Consume an approval and export the approved run")
    revoke = review_commands.add_parser("revoke", help="Revoke an unused approval")
    close = review_commands.add_parser("close-task", help="End a task and revoke its pending export approvals")
    close.add_argument("--task", required=True)
    for operation in (approve, redeem):
        operation.add_argument("directory", type=Path)
        operation.add_argument("--task", required=True)
        operation.add_argument("--output", type=Path, required=True)
        operation.add_argument("--brief", type=Path, help="Include a verified remediation brief")
    approve.add_argument("--ttl", type=int, default=300, help="Approval lifetime in seconds (1–3600)")
    for operation in (redeem, revoke):
        operation.add_argument("--approval", type=Path, required=True)
    experiment_plan = commands.add_parser("experiment-plan", help="Print a bounded v2 plan; does not provision or execute tools")
    experiment_plan.add_argument("--pack", choices=["python", "typescript", "c", "rust"], required=True)
    experiments = commands.add_parser("experiments", help="Run a validated v2 plan; blocked without separately reviewed v2 provisioning")
    experiments.add_argument("--plan", type=Path, required=True)
    experiments.add_argument("--output", type=Path, required=True)
    planner = commands.add_parser("plan-next", help="Rank bounded experiments for a declared synthetic hypothesis model; executes nothing")
    planner.add_argument("--input", type=Path, help="Planning request JSON (64 KiB maximum)")
    planner.add_argument("--example", action="store_true", help="Print an editable example request instead")
    evaluate = commands.add_parser("evaluate-planner", help="Run the preregistered synthetic planner evaluation into a NEW directory")
    evaluate.add_argument("--output", type=Path, required=True)
    verify_evaluation = commands.add_parser("verify-planner-evaluation", help="Recompute a retained planner evaluation and compare it byte for byte")
    verify_evaluation.add_argument("directory", type=Path)
    compare = commands.add_parser("compare-experiments", help="Compare two independently verified fixed-v2 runs without execution")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    compare.add_argument("--output", type=Path, required=True)
    brief = commands.add_parser("brief", help="Write a sourced remediation brief for a verified run: offline --demo, or opt-in --live with Tavily and a Bifrost gateway")
    brief.add_argument("run", type=Path, help="A completed run directory that passes verify-artifacts")
    brief.add_argument("--output", type=Path, required=True, help="NEW directory for brief.json and brief.html")
    brief.add_argument("--demo", action="store_true", help="Scripted providers and invented excerpts; no network, no credentials")
    brief.add_argument("--live", action="store_true", help="Real research and model calls; needs --confirm-outbound")
    brief.add_argument("--confirm-outbound", action="store_true", help="Consent to send the fixed queries to Tavily and public excerpts to the gateway")
    freshness = commands.add_parser("freshness", help="Check a public AI answer for outdated claims")
    freshness.add_argument("answer", type=Path)
    freshness.add_argument("--domain", action="append", required=True, help="Trusted publisher domain, repeatable")
    freshness.add_argument("--output", type=Path, required=True, help="New directory for HTML and JSON reports")
    freshness.add_argument("--confirm-outbound", action="store_true", help="Send the answer to Bifrost and search terms to Tavily")
    for command in (brief, freshness):
        command.add_argument("--gateway-url", help="Bifrost origin: loopback HTTP or a remote HTTPS hostname")
        command.add_argument("--model", help="Bifrost model, for example provider/model")
        command.add_argument("--fallback", action="append", default=[], help="Requested Bifrost fallback model; repeatable, at most 3")
        command.add_argument("--gateway-token-env", help="Name of the environment variable holding the Bifrost virtual key")
        command.add_argument("--tavily-key-env", help="Name of the environment variable holding the Tavily API key")
        command.add_argument("--search-relay", help="Search through this Bifrost relay (the Tavily key stays in the gateway)")
        command.add_argument("--gateway-timeout", type=float, help="Seconds allowed per model call, 1-180 (default 60)")
        command.add_argument("--json-mode", action="store_true", help="Also send response_format json_object (honoured by OpenAI-compatible providers; a gateway may ignore it, a provider may reject it)")
    verify_brief = commands.add_parser("verify-brief", help="Check a brief against its source run and its retained excerpts; makes no network call")
    verify_brief.add_argument("run", type=Path)
    verify_brief.add_argument("brief", type=Path)
    commands.add_parser("pentest-scope-example", help="Print an editable example pentest scope file")
    pentest = commands.add_parser("pentest", help="Run the autonomous, scope-bounded pentest agent into a NEW output directory. "
                                  "Offline deterministic planner by default; add --model/--gateway-url/--gateway-token-env for "
                                  "Bifrost-backed reasoning. Every proposed action is re-validated against --scope before execution.")
    pentest.add_argument("--scope", type=Path, required=True, help="Scope file; see pentest-scope-example")
    pentest.add_argument("--output", type=Path, required=True)
    pentest.add_argument("--model", help="Bifrost model, for example provider/model; enables the reasoning planner")
    pentest.add_argument("--gateway-url", help="Bifrost origin: loopback HTTP or a remote HTTPS hostname")
    pentest.add_argument("--gateway-token-env", help="Name of the environment variable holding the Bifrost virtual key")
    pentest.add_argument("--fallback", action="append", default=[], help="Requested Bifrost fallback model; repeatable, at most 3")
    pentest.add_argument("--gateway-timeout", type=float, help="Seconds allowed per model call, 1-180 (default 60)")
    pentest.add_argument("--json-mode", action="store_true", help="Also send response_format json_object (a gateway/provider may ignore or reject it)")
    pbrief = commands.add_parser("pentest-brief", help="Write a sourced remediation brief for a verified pentest run: offline --demo, or opt-in --live with Tavily and a Bifrost gateway")
    pbrief.add_argument("run", type=Path, help="A completed pentest run directory that passes verify-artifacts")
    pbrief.add_argument("--output", type=Path, required=True, help="NEW directory for remediation.json")
    pbrief.add_argument("--demo", action="store_true", help="Scripted providers and invented excerpts; no network, no credentials")
    pbrief.add_argument("--live", action="store_true", help="Real research and model calls; needs --confirm-outbound")
    pbrief.add_argument("--confirm-outbound", action="store_true", help="Consent to send the fixed queries to Tavily and public excerpts to the gateway")
    pbrief.add_argument("--gateway-url", help="Bifrost origin: loopback HTTP or a remote HTTPS hostname")
    pbrief.add_argument("--model", help="Bifrost model, for example provider/model")
    pbrief.add_argument("--fallback", action="append", default=[], help="Requested Bifrost fallback model; repeatable, at most 3")
    pbrief.add_argument("--gateway-token-env", help="Name of the environment variable holding the Bifrost virtual key")
    pbrief.add_argument("--tavily-key-env", help="Name of the environment variable holding the Tavily API key")
    pbrief.add_argument("--search-relay", help="Search through this Bifrost relay (the Tavily key stays in the gateway)")
    pbrief.add_argument("--gateway-timeout", type=float, help="Seconds allowed per model call, 1-180 (default 60)")
    pbrief.add_argument("--json-mode", action="store_true", help="Also send response_format json_object (a gateway/provider may ignore or reject it)")
    verify_pbrief = commands.add_parser("verify-pentest-brief", help="Check a pentest remediation brief against its source run; makes no network call")
    verify_pbrief.add_argument("run", type=Path)
    verify_pbrief.add_argument("brief", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "compare-experiments":
            from .experiment_comparison import compare_experiments
            from .contracts import canonical, require
            from .engine import write_new
            output = args.output.absolute()
            check_no_links(output.parent)
            require(not output.exists(), "Comparison output must be new")
            require(not any(output.is_relative_to(root.absolute()) for root in (args.before, args.after)),
                    "Comparison output must be outside source runs")
            result = compare_experiments(args.before, args.after)
            raw = canonical(result)
            require(len(raw) <= 2_000_000, "Comparison exceeds output ceiling")
            write_new(output, raw)
            print(json.dumps({"status": result["status"], "output": str(output)}, indent=2))
            return 0
        if args.command == "plan-next":
            from .planning import example_request, plan_next
            if args.example == (args.input is not None):
                raise ValidationError("Use exactly one of --example or --input")
            if args.example:
                print(json.dumps(example_request(), indent=2))
                return 0
            check_no_links(args.input.absolute())
            with args.input.open("rb") as stream:
                raw = stream.read(65537)
            if len(raw) > 65536:
                raise ValidationError("Planning request exceeds 64 KiB")
            print(json.dumps(plan_next(parse_json(raw)), indent=2))
            return 0
        if args.command == "evaluate-planner":
            from .planner_eval import evaluate_planner
            print(json.dumps(evaluate_planner(args.output), indent=2))
            return 0
        if args.command == "verify-planner-evaluation":
            from .planner_eval import verify_planner_evaluation
            print(json.dumps(verify_planner_evaluation(args.directory), indent=2))
            return 0
        if args.command == "export-viewer":
            from .export_viewer import export_viewer
            print(json.dumps(export_viewer(args.directories, args.output, brief_dir=args.brief), indent=2))
            return 0
        if args.command == "review-export":
            from .review_export import approve_export, close_task, load_key, read_approval, redeem_export, revoke_export
            if args.review_command == "close-task":
                result = close_task(task=args.task, ledger=args.ledger)
            else:
                key = load_key(os.environ)
                if args.review_command == "approve":
                    result = approve_export(args.directory, args.output, task=args.task, ledger=args.ledger,
                                            key=key, ttl=args.ttl, brief_dir=args.brief)
                elif args.review_command == "redeem":
                    result = redeem_export(args.directory, args.output, task=args.task, ledger=args.ledger,
                                           key=key, approval=read_approval(args.approval), brief_dir=args.brief)
                else:
                    result = revoke_export(ledger=args.ledger, key=key, approval=read_approval(args.approval))
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "experiment-plan":
            from .local_profiles import default_experiment_plan
            print(json.dumps(default_experiment_plan(args.pack), indent=2))
            return 0
        if args.command == "experiments":
            from .local_engine import run_experiments
            check_no_links(args.plan.absolute())
            with args.plan.open("rb") as stream:
                plan = parse_json(stream.read(65537))
            if args.plan.stat().st_size > 65536:
                raise ValidationError("Experiment plan exceeds 64 KiB")
            result = run_experiments(args.output, plan)
            print(json.dumps({"run_id": result["run_id"], "mode": "local", "status": result["status"],
                              "output": str(args.output.absolute())}, indent=2))
            return 0 if result["status"] == "completed" else 2
        if args.command == "brief":
            from .brief import brief_from_args
            result = brief_from_args(args, os.environ)
            print(json.dumps(result, indent=2))
            return 0 if result["status"] == "completed" else 2
        if args.command == "freshness":
            from .freshness import freshness_from_args
            result = freshness_from_args(args, os.environ)
            print(json.dumps({"status": result["status"], "claims": len(result["claims"]),
                              "output": str(args.output.absolute())}, indent=2))
            return 0 if result["status"] == "completed" else 2
        if args.command == "verify-brief":
            from .brief import verify_brief
            print(json.dumps(verify_brief(args.run, args.brief), indent=2))
            return 0
        if args.command == "pentest-scope-example":
            from .pentest.scope import example_scope
            print(json.dumps(example_scope(), indent=2))
            return 0
        if args.command == "pentest":
            from .pentest.cli_support import pentest_from_args
            manifest = pentest_from_args(args, os.environ)
            print(json.dumps({"run_id": manifest["run_id"], "mode": manifest["mode"], "status": manifest["status"],
                              "output": str(args.output.absolute())}, indent=2))
            return 0 if manifest["status"] == "completed" else 2
        if args.command == "pentest-brief":
            from .pentest.remediation import remediation_from_args
            result = remediation_from_args(args, os.environ)
            print(json.dumps(result, indent=2))
            return 0 if result["status"] == "completed" else 2
        if args.command == "verify-pentest-brief":
            from .pentest.remediation import verify_pentest_remediation
            print(json.dumps(verify_pentest_remediation(args.run, args.brief), indent=2))
            return 0
        if args.command == "packs":
            from .packs import REGISTRY
            from .local_engine import OPERATIONS
            result = {"project_id": "labproof", "assessment": "blocked",
                      "assessment_scope": "broad_catalogue_not_runtime_acceptance",
                      "local_mode": {"readiness": "not_probed",
                                     "fixed_operations": {pack: value[0] for pack, value in OPERATIONS.items()}},
                      "packs": [{**pack.to_dict(), "provisioned": pack.provisioned}
                                for pack in REGISTRY.packs],
                      "limitations": ["Declared operations are not installed or verified capabilities.",
                                      "No runtime probe, fixture execution, or model call is performed."]}
            print(json.dumps(result, indent=2))
            return 0
        if args.command == "assess" and args.mode == "local":
            if args.pack is None or args.output is None:
                raise ValidationError("Local assessment requires --pack and --output")
            from .local_engine import run_local
            result = run_local(args.output, args.pack)
            print(json.dumps({"run_id": result["run_id"], "mode": "local", "status": result["status"],
                              "output": str(args.output.absolute())}, indent=2))
            return 0 if result["status"] == "completed" else 2
        if args.command in {"doctor", "assess"}:
            result = doctor()
            result["command"] = args.command
            print(json.dumps(result, indent=2))
            return 2  # Nonzero: actual assessment is NOT ready.
        if args.command == "verify-artifacts":
            result = verify_artifacts(args.directory)
            print(json.dumps(result, indent=2))
            return 0 if result["complete"] else 2
        result = run_demo(args.output, limits=Limits(max_actions=args.max_actions))
        print(json.dumps({"run_id": result["run_id"], "mode": result["mode"], "status": result["status"], "output": str(args.output.absolute())}, indent=2))
        return 0 if result["status"] == "completed" else 2
    except (ValidationError, PolicyError, PackError, OSError) as exc:
        print(json.dumps({"error": type(exc).__name__, "message": str(exc)}), file=sys.stderr)
        return 1
