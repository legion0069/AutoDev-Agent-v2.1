from core.orchestrator import Orchestrator
from core.symbol_graph import SymbolGraph


class _EvolutionControllerSpy:
    def __init__(self):
        self.calls = []

    def run_cycle(self, **kwargs):
        self.calls.append(kwargs)
        return {"cycle_id": "test-cycle"}


def test_orchestrator_evolution_remains_opt_in(tmp_path):
    controller = _EvolutionControllerSpy()
    orchestrator = Orchestrator(
        project_root=tmp_path / "default",
        plan_path=tmp_path / "default" / "memory" / "project_plan.json",
        state_path=tmp_path / "default" / "memory" / "state.json",
        tasks_path=tmp_path / "default" / "memory" / "tasks.json",
        log_dir=tmp_path / "default" / "logs",
        evolution_controller=controller,
    )
    try:
        assert orchestrator.evolution_mode is False
        orchestrator._run_evolution_cycle(SymbolGraph(), 0.1, True)
        assert controller.calls == []
        assert orchestrator.latest_evolution_report is None
    finally:
        if orchestrator.multi_agent_runtime is not None:
            orchestrator.multi_agent_runtime.close()


def test_orchestrator_runs_injected_evolution_controller_when_enabled(tmp_path):
    controller = _EvolutionControllerSpy()
    orchestrator = Orchestrator(
        project_root=tmp_path / "enabled",
        plan_path=tmp_path / "enabled" / "memory" / "project_plan.json",
        state_path=tmp_path / "enabled" / "memory" / "state.json",
        tasks_path=tmp_path / "enabled" / "memory" / "tasks.json",
        log_dir=tmp_path / "enabled" / "logs",
        evolution_mode=True,
        evolution_controller=controller,
    )
    try:
        orchestrator._run_evolution_cycle(SymbolGraph(), 0.1, True)

        assert len(controller.calls) == 1
        assert orchestrator.latest_evolution_report == {"cycle_id": "test-cycle"}
        observations = controller.calls[0]["observations"]
        assert observations["execution"]["success"] is True
        assert set(observations["optimization_metrics"]) == {
            "planning",
            "scheduling",
            "prompting",
            "reasoning",
            "collaboration",
            "learning",
            "execution",
            "caching",
        }
    finally:
        if orchestrator.multi_agent_runtime is not None:
            orchestrator.multi_agent_runtime.close()
