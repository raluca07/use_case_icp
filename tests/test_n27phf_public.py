import ast
from pathlib import Path

from use_case_icp import corrected_experiment as ce
from use_case_icp import n27phf_experiment as experiment
from use_case_icp import n27phf_public as public


ROOT = Path(__file__).resolve().parents[1]


def test_public_configuration_removes_private_prior_attempt_dependency(tmp_path):
    try:
        target = public.configure(ROOT, Path("outputs/attempt-057-public-test"))

        assert target == ROOT / "outputs/attempt-057-public-test"
        assert experiment.PRESERVED_HASHES == {}
        assert experiment.lifecycle.PRESERVED_HASHES == {}
        assert experiment.lifecycle._verify_authority(ROOT)["task"].startswith("sha256:")

        record = public._public_preservation_manifest(ROOT, tmp_path / "attempt")
        assert record["status"] == "not_required"
        assert record["bound_file_hashes"] == {}
    finally:
        public.reset()


def test_public_cli_help(capsys):
    try:
        public.main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0
    assert "build" in capsys.readouterr().out


def test_public_scoring_uses_instance_truth_job():
    instance = {"truth_job": experiment.JOB3, "truth_function": "allocate_campaign_budget"}
    validation = {
        "fault_detected": True,
        "suspect_job": "job_3",
        "normalized_suspect_function": "allocate_campaign_budget",
        "suspect_function_visible": True,
    }

    outcome = public.score_response(instance, validation)

    assert outcome["correct_job_attribution"]
    assert outcome["exact_function_localisation"]
    assert outcome["truth_job"] == "job_3"


def test_cleaned_job3_removes_audit_without_changing_clean_output():
    cleaned = (ROOT / experiment.JOB3_SOURCE).read_text()
    prior = (ROOT / "src/use_case_icp/n27phb_campaign_allocation.py").read_text()
    assert "contribution_audit_df" not in cleaned
    assert "contribution_audit_df" in prior

    root = experiment.input_for(experiment.CONTROLS[0])
    jobs = experiment._run_sources(ROOT, root, experiment.CONTROLS[0])
    job3_input = jobs["inputs"][experiment.JOB3]
    assert experiment.base._run_program(prior, job3_input, ROOT) == experiment.base._run_program(
        cleaned, job3_input, ROOT
    )


def test_six_faults_are_single_ast_site_mutations():
    for instance in experiment.FAULTS:
        job1, job3, mutation = experiment._source_for_instance(ROOT, instance)
        clean = (ROOT / experiment.JOB_SOURCES[mutation["job_id"]]).read_text()
        mutant = job3 if instance in experiment.C else job1
        assert mutation["candidate_count"] == 1
        assert clean.count(mutation["original_snippet"]) == 1
        assert ast.dump(ast.parse(clean)) != ast.dump(ast.parse(mutant))
        assert ce.sha256(mutant.encode()) == mutation["mutated_source_sha256"]
