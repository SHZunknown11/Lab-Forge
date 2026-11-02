import time

import pytest

from core.execution.runner import SPRING_LIBS, CodeRunner, prepare_java, safe_rel
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


def test_prepare_java_entry_ignores_nested_types_above_main():
    code = ("public class Bank {\n    // class Fake {\n    static class Account { int bal; }\n"
            "    record Txn(String kind) {}\n    public static void main(String[] a) { System.out.println(\"class X {\"); }\n}\n")
    _, entry, public = prepare_java(code)
    assert entry == "Bank" and public == "Bank"


@needs_java
def test_java_nested_class_before_main_runs(tmp_path):
    code = ("public class Main {\n    static class Node { int v; Node(int v) { this.v = v; } }\n"
            "    public static void main(String[] args) { System.out.println(new Node(7).v); }\n}\n")
    result = runner.run("java", [CodeFile(name="Main.java", code=code)], "", tmp_path)
    assert result.status == "passed" and result.output == "7"


@needs_java
def test_java_output_survives_a_timeout(tmp_path):
    code = 'public class Spin { public static void main(String[] a) { System.out.print("Started"); while (true) {} } }'
    result = CodeRunner(timeout_seconds=3).run("java", [CodeFile(name="Spin.java", code=code)], "", tmp_path)
    assert result.status == "failed" and "Started" in result.output


SPRING_APP = """package com.demo;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.*;
@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) { SpringApplication.run(DemoApplication.class, args); }
}
@RestController class Hello { @GetMapping("/hi") String hi(@RequestParam String name) { return "Hi " + name; } }
@Component class Runner implements CommandLineRunner {
    public void run(String... args) { System.out.println("started"); }
}
"""


@needs_java
@pytest.mark.skipif(not (SPRING_LIBS / "VERSION").exists(), reason="run setup_runtime.py --spring")
def test_spring_boot_web_app_runs_and_exits(tmp_path):
    result = CodeRunner(timeout_seconds=60).run("java", [CodeFile(name="DemoApplication.java", code=SPRING_APP)], "", tmp_path)
    assert result.status == "passed" and result.output == "started"


@pytest.mark.parametrize("name,expected", [
    ("../../etc/passwd", "etc/passwd"),
    ("C:\\Windows\\x.java", "Windows/x.java"),
    ("src/App.jsx", "src/App.jsx"),
    ("", "main.py"),
])
def test_file_names_cannot_escape_the_work_folder(name, expected):
    assert safe_rel(name, "python") == expected


def test_python_network_guard_blocks_internet_but_not_loopback(tmp_path, monkeypatch):
    monkeypatch.setenv("EXEC_ALLOW_NETWORK", "0")
    code = (
        "import socket\n"
        "srv = socket.socket(); srv.bind(('127.0.0.1', 0)); srv.listen(1)\n"
        "socket.create_connection(srv.getsockname(), timeout=2).close(); print('loopback ok')\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 80), timeout=2)\n"
        "except OSError as e:\n"
        "    print('blocked', e.errno)\n"
    )
    result = runner.run("python", [CodeFile(name="main.py", code=code)], "", tmp_path)
    assert result.output.splitlines() == ["loopback ok", "blocked 101"]


@needs_node
def test_node_network_guard_blocks_internet_but_not_loopback(tmp_path, monkeypatch):
    monkeypatch.setenv("EXEC_ALLOW_NETWORK", "0")
    code = (
        "const net = require('net');\n"
        "const srv = net.createServer((s) => s.end()).listen(0, '127.0.0.1', () => {\n"
        "  net.connect(srv.address().port, '127.0.0.1', () => {\n"
        "    console.log('loopback ok');\n"
        "    net.connect(80, '1.1.1.1').on('error', (e) => { console.log('blocked', e.code); srv.close(); });\n"
        "  });\n"
        "});\n"
    )
    result = runner.run("javascript", [CodeFile(name="index.js", code=code)], "", tmp_path)
    assert result.output.splitlines() == ["loopback ok", "blocked ENETUNREACH"]


def test_timeout_kills_the_program_and_its_children(tmp_path):
    quick = CodeRunner(timeout_seconds=3)
    code = (
        "import subprocess, sys, time\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "print('started', flush=True)\n"
        "time.sleep(60)\n"
    )
    start = time.monotonic()
    result = quick.run("python", [CodeFile(name="main.py", code=code)], "", tmp_path)
    assert result.status == "failed" and "started" in result.output
    assert time.monotonic() - start < 20  # the sleeping grandchild doesn't hold the run open
