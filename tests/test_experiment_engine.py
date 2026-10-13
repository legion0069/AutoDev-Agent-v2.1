import pytest

from core.experiment_engine import (
    ExperimentEngine,
    EvolutionExperimentEngine,
)


def test_evolution_experiment_runs_compares_and_rolls_back(tmp_path):
    engine = EvolutionExperimentEngine(tmp_path)
    experiment = engine.create_experiment(
        "compare implementations",
        lambda workspace: 10.0,
        {"candidate": lambda workspace: 1.0},
        sample_size=3,
    )

    result = engine.run(experiment["experiment_id"])
    assert result["status"] == "completed"
    assert len(result["baseline_samples"]) == 3
    assert result["candidate_results"]["candidate"]["is_improvement"]
    assert engine.rollback(experiment["experiment_id"])["winner"] is None


def test_legacy_experiment_engine_api_remains_available():
    engine = ExperimentEngine()
    experiment = engine.create_experiment(
        "legacy",
        "testable hypothesis",
        "candidate",
        "baseline",
    )
    assert experiment.experiment_id


def test_evolution_experiment_rejects_invalid_sample_size():
    with pytest.raises(ValueError, match="sample_size"):
        EvolutionExperimentEngine().create_experiment(
            "invalid", sample_size=1
        )


def test_evolution_experiment_discards_failed_sample_workspace(tmp_path):
    engine = EvolutionExperimentEngine(tmp_path)

    def broken_runner(workspace):
        (workspace / "candidate.txt").write_text("discard me", encoding="utf-8")
        raise RuntimeError("candidate failed")

    experiment = engine.create_experiment(
        "failed candidate",
        lambda _: 1.0,
        {"broken": broken_runner},
        sample_size=2,
    )

    with pytest.raises(RuntimeError, match="candidate failed"):
        engine.run(experiment["experiment_id"])

    failed = engine.history()[0]
    assert failed["status"] == "failed"
    assert failed["rollback_status"] == "isolated_workspace_discarded"
    assert list(tmp_path.iterdir()) == []
