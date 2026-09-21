import pytest
from core.execution.runner import JavaRunner

def test_java_runner_success():
    runner = JavaRunner(timeout_seconds=5)
    code = '''
    import java.util.Scanner;
    public class TestApp {
        public static void main(String[] args) {
            Scanner scanner = new Scanner(System.in);
            String name = scanner.nextLine();
            System.out.println("Hello, " + name);
        }
    }
    '''
    comp, exec_res = runner.execute("TestApp.java", code, test_input="LabForge\n")
    assert comp.exit_code == 0
    assert exec_res is not None
    assert exec_res.exit_code == 0
    assert "Hello, LabForge" in exec_res.stdout

def test_java_runner_compile_error():
    runner = JavaRunner(timeout_seconds=5)
    code = '''
    public class TestApp {
        public static void main(String[] args) {
            System.out.println("Missing semicolon")
        }
    }
    '''
    comp, exec_res = runner.execute("TestApp.java", code)
    assert comp.exit_code != 0
    assert "error: ';' expected" in comp.stderr
    assert exec_res is None
