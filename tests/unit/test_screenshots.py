import pytest
from pathlib import Path
from core.screenshots.terminal_renderer import TerminalRenderer
from core.schemas import ExecutionEvidence, ExecutionResult

def test_terminal_renderer(tmp_path):
    renderer = TerminalRenderer()
    
    evidence = ExecutionEvidence(
        level="easy",
        source_code="public class Test {}",
        compilation_result=ExecutionResult(stdout="", stderr="", exit_code=0, duration_ms=100),
        execution_result=ExecutionResult(stdout="Hello\nWorld\n", stderr="", exit_code=0, duration_ms=100),
        success=True
    )
    
    artifact = renderer.render(evidence, tmp_path)
    
    assert artifact.level == "easy"
    assert Path(artifact.image_path).exists()
    assert artifact.width >= 400
    assert artifact.height >= 100
