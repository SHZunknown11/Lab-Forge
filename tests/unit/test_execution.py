import pytest

from core.execution.runner import CodeRunner, prepare_java, safe_rel
from core.schemas import CodeFile

runner = CodeRunner()
caps = runner.available()
needs_java = pytest.mark.skipif(not caps.get("java"), reason="JDK not installed")
needs_node = pytest.mark.skipif(not caps.get("javascript"), reason="Node not installed")

SQRT = """import java.util.Scanner;
public class Sqrt {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        System.out.print("Enter a number: ");
        double n = sc.nextDouble();
        if (n < 0) throw new IllegalArgumentException("negative");
        System.out.println("Root: " + Math.sqrt(n));
    }
}"""


@needs_java
def test_java_console_shows_typed_input(tmp_path):
    result = runner.run("java", [CodeFile(name="Sqrt.java", code=SQRT)], "16", tmp_path)
    assert result.status == "passed"
    assert result.output.splitlines() == ["Enter a number: 16", "Root: 4.0"]


@needs_java
def test_java_uncaught_exception_is_a_failure_with_clean_trace(tmp_path):
    result = runner.run("java", [CodeFile(name="Sqrt.java", code=SQRT)], "-4", tmp_path)
    assert result.status == "failed" and result.retryable
    assert 'Exception in thread "main" java.lang.IllegalArgumentException: negative' in result.output
    assert "LFLauncher" not in result.output and "reflect" not in result.output


@needs_java
def test_java_compile_error_is_retryable(tmp_path):
    result = runner.run("java", [CodeFile(name="Bad.java", code="public class Bad { void x( }")], "", tmp_path)
    assert result.status == "failed" and result.retryable and "compile" in result.note


def test_python_input_echo_and_secrets_are_not_inherited(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret")
    code = 'import os\nname = input("Name: ")\nprint("Hi", name)\nprint("key" , os.environ.get("GEMINI_API_KEY"))'
    result = runner.run("python", [CodeFile(name="main.py", code=code)], "Asha", tmp_path)
    assert result.status == "passed"
    assert "Name: Asha" in result.output
    assert "super-secret" not in result.output


def test_missing_python_package_asks_for_a_screenshot(tmp_path):
    result = runner.run("python", [CodeFile(name="main.py", code="import not_a_real_pkg_xyz")], "", tmp_path)
    assert result.status == "not_run" and "screenshot" in result.note


@needs_node
def test_node_runs(tmp_path):
    result = runner.run("javascript", [CodeFile(name="index.js", code="console.log(2 + 3)")], "", tmp_path)
    assert result.status == "passed" and result.output == "5"


def test_unsupported_language_is_not_run(tmp_path):
    result = runner.run("matlab", [CodeFile(name="a.m", code="disp(1)")], "", tmp_path)
    assert result.status == "not_run" and "screenshot" in result.note


def test_prepare_java_keeps_one_public_class():
    code = "package a.b;\npublic class Helper {}\npublic class App { public static void main(String[] a) {} }"
    fixed, entry, public = prepare_java(code)
    assert entry == "App" and public == "App"
    assert "package" not in fixed and "public class Helper" not in fixed


@pytest.mark.parametrize("name,expected", [
    ("../../etc/passwd", "etc/passwd"),
    ("C:\\Windows\\x.java", "Windows/x.java"),
    ("src/App.jsx", "src/App.jsx"),
    ("", "main.py"),
])
def test_file_names_cannot_escape_the_work_folder(name, expected):
    assert safe_rel(name, "python") == expected
