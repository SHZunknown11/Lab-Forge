"""Java compilation and execution engine with isolation and timeouts."""
from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from core.schemas import ExecutionResult


class JavaRunner:
    """Compile and run Java source code in temporary directories."""

    def __init__(self, timeout_seconds: int = 10):
        self.timeout = timeout_seconds

    def execute(
        self,
        filename: str,
        code: str,
        test_input: str = "",
    ) -> tuple[ExecutionResult, Optional[ExecutionResult]]:
        """
        Compile and run Java code.

        Returns (compilation_result, execution_result).
        execution_result is None if compilation fails.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            src_path = Path(tmpdir) / filename
            src_path.write_text(code, encoding="utf-8")

            # Compile
            comp_result = self._compile(src_path, tmpdir)
            if comp_result.exit_code != 0:
                return comp_result, None

            # Run
            class_name = filename.replace(".java", "")
            exec_result = self._run(class_name, tmpdir, test_input)
            return comp_result, exec_result

    def _compile(self, src_path: Path, work_dir: str) -> ExecutionResult:
        start = time.time()
        try:
            result = subprocess.run(
                ["javac", str(src_path)],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            duration = int((time.time() - start) * 1000)
            return ExecutionResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=duration,
            )
        except subprocess.TimeoutExpired:
            duration = int((time.time() - start) * 1000)
            return ExecutionResult(
                stderr="Compilation timed out",
                exit_code=1,
                duration_ms=duration,
            )
        except FileNotFoundError:
            return ExecutionResult(
                stderr="javac not found. JDK is required.",
                exit_code=1,
                duration_ms=0,
            )

    def _run(
        self, class_name: str, work_dir: str, test_input: str = ""
    ) -> ExecutionResult:
        start = time.time()
        try:
            result = subprocess.run(
                ["java", "-cp", work_dir, class_name],
                cwd=work_dir,
                capture_output=True,
                text=True,
                input=test_input,
                timeout=self.timeout,
            )
            duration = int((time.time() - start) * 1000)
            return ExecutionResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=duration,
            )
        except subprocess.TimeoutExpired:
            duration = int((time.time() - start) * 1000)
            return ExecutionResult(
                stderr="Execution timed out",
                exit_code=1,
                duration_ms=duration,
            )
        except FileNotFoundError:
            return ExecutionResult(
                stderr="java not found. JDK is required.",
                exit_code=1,
                duration_ms=0,
            )
