"""Checks for the product-local viewer export."""
import json
from pathlib import Path

import pytest

from labproof.cli import main
from labproof.contracts import ValidationError
from labproof.engine import run_demo
from labproof.export_viewer import export_viewer
from labproof.local_engine import run_experiments
from labproof.local_profiles import default_experiment_plan
from test_local_artifacts import make_run, mutate_json


def test_offline_cli_export(tmp_path, capsys):
    run = tmp_path / "demo"
    assert main(["demo", "--output", str(run)]) == 0
    capsys.readouterr()
    output = tmp_path / "viewer.json"
    assert main(["export-viewer", str(run), "--output", str(output)]) == 0
    result = json.loads(capsys.readouterr().out)
    bundle = json.loads(output.read_bytes())
    assert set(bundle) == {"schema_version", "generated_at", "runs", "annotations", "limitations"}
    assert bundle["schema_version"] == "1.0" and bundle["annotations"] == []
    assert set(bundle["runs"][0]) == {"manifest", "report", "events"}
    assert bundle["runs"][0]["manifest"]["project_id"] == "labproof"
    assert result["bytes"] == output.stat().st_size <= 5 * 1024 * 1024
    original = output.read_bytes()
    assert main(["export-viewer", str(run), "--output", str(output)]) == 1
    assert output.read_bytes() == original


def test_cli_export_attaches_only_the_verified_brief_for_the_first_run(tmp_path, capsys):
    run, other, brief = (tmp_path / name for name in ("replay", "other", "brief"))
    run_demo(run)
    run_demo(other)
    assert main(["brief", str(run), "--demo", "--output", str(brief)]) == 0
    capsys.readouterr()
    output = tmp_path / "review.json"
    assert main(["export-viewer", str(run), str(other), "--brief", str(brief), "--output", str(output)]) == 0
    assert json.loads(output.read_bytes())["remediation"] == json.loads((brief / "brief.json").read_bytes())

    rejected = tmp_path / "rejected.json"
    with pytest.raises(ValidationError, match="does not belong"):
        export_viewer([other, run], rejected, brief_dir=brief)
    (brief / "brief.html").write_text("changed", encoding="utf-8")
    with pytest.raises(ValidationError, match="does not match"):
        export_viewer([run], rejected, brief_dir=brief)
    assert not rejected.exists()


@pytest.mark.parametrize("status,count,accepted", [("completed", 8, True), ("blocked", 0, False), ("incomplete", 3, True)])
def test_local_v1_export_status_preserved(tmp_path, status, count, accepted):
    run = make_run(tmp_path / "run", status=status, count=count, accepted=accepted)
    export_viewer([run], tmp_path / "bundle.json")
    assert json.loads((tmp_path / "bundle.json").read_bytes())["runs"][0]["manifest"]["status"] == status


def test_export_v2_blocked_does_not_downgrade(tmp_path):
    run = tmp_path / "v2"
    run_experiments(run, default_experiment_plan("python"))
    export_viewer([run], tmp_path / "bundle.json")
    report = json.loads((tmp_path / "bundle.json").read_bytes())["runs"][0]["report"]
    assert report["schema_version"] == "local-report-2" and report["status"] == "blocked"


def test_duplicate_wrong_project_tamper_and_in_run_output(tmp_path):
    run = make_run(tmp_path / "run")
    for directories, output in (([run, run], tmp_path / "duplicate.json"), ([run], run / "bad.json")):
        with pytest.raises(ValidationError):
            export_viewer(directories, output)
        assert not output.exists()
    mutate_json(run, "report.json", lambda r: r.update(summary="tampered"))
    with pytest.raises(ValidationError):
        export_viewer([run], tmp_path / "tampered.json")
    mutate_json(run, "manifest.json", lambda m: m.update(project_id="other-product"))
    with pytest.raises(ValidationError):
        export_viewer([run], tmp_path / "wrong.json")


def test_actual_five_mib_limit_no_partial_output(tmp_path):
    runs = []
    # V1 permits extension metadata. All four source reports remain below their
    # 2 MB artifact ceiling but their verified viewer envelope exceeds 5 MiB.
    for i in range(4):
        root = tmp_path / str(i)
        run_demo(root)
        mutate_json(root, "report.json", lambda r: r.update(export_test_metadata="x" * 1_400_000))
        runs.append(root)
    output = tmp_path / "oversize.json"
    with pytest.raises(ValidationError, match="5 MiB"):
        export_viewer(runs, output)
    assert not output.exists()


def test_rejects_export_below_byte_ceiling_with_text_too_long_for_browser(tmp_path):
    run = tmp_path / "run"
    run_demo(run)
    mutate_json(run, "report.json", lambda report: report.update(export_test_metadata="x" * 200_001))
    output = tmp_path / "review.json"
    with pytest.raises(ValidationError, match="200,000 UTF-16"):
        export_viewer([run], output)
    assert not output.exists()


def test_published_viewer_schema_accepts_saved_review_and_fresh_export(tmp_path):
    jsonschema = pytest.importorskip("jsonschema")
    from referencing import Registry, Resource

    repo = Path(__file__).resolve().parents[1]
    schema = json.loads((repo / "docs/viewer-bundle.schema.json").read_bytes())
    manifest = json.loads((repo / "docs/run-envelope.schema.json").read_bytes())
    registry = Registry().with_resource("run-envelope.schema.json", Resource.from_contents(manifest))
    jsonschema.Draft202012Validator.check_schema(schema)
    validator = jsonschema.Draft202012Validator(schema, registry=registry, format_checker=jsonschema.FormatChecker())
    validator.validate(json.loads((repo / "viewer/public/review.json").read_bytes()))

    run = tmp_path / "run"
    run_demo(run)
    output = tmp_path / "review.json"
    export_viewer([run], output)
    validator.validate(json.loads(output.read_bytes()))
