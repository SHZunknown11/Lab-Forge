"""Compile and run student programs, capturing the real console session.

Runs Java, Python, C, C++, Node.js (Express, Mongoose against a throwaway
in-memory MongoDB), React (bundled with esbuild, screenshotted in headless
Chrome) and plain HTML/CSS/JS pages. Anything else is reported as "not run"
so the student attaches their own screenshot. Output is never invented.

Backends
  EXEC_BACKEND=local   subprocess in a temp folder with a scrubbed environment (development)
  EXEC_BACKEND=docker  throwaway container per run: no network, CPU/memory/pid limits
                       (use for any public deployment; see docs/deployment.md)

EXEC_ALLOW_NETWORK=0 keeps programs off the internet: in a private network
namespace when the kernel allows it (unshare), otherwise through loopback-only
guards in the Python, Node and Java launchers. On Linux every run gets its own
process group (killed as a whole on timeout), CPU/file-size limits, and at
most LABFORGE_MAX_PARALLEL_RUNS programs run at once.
"""
from __future__ import annotations

import functools
import http.server
import os
import re
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from core.schemas import CodeFile, RunResult

ROOT = Path(__file__).resolve().parents[2]
HARNESS = Path(__file__).parent / "harness"
NODE_RUNTIME = Path(os.environ.get("EXEC_NODE_MODULES", ROOT / ".runtime" / "node" / "node_modules"))
MAX_OUTPUT_CHARS = 20_000
POSIX = os.name != "nt"
_SLOTS = threading.BoundedSemaphore(max(1, int(os.environ.get("LABFORGE_MAX_PARALLEL_RUNS", "3"))))


def network_allowed() -> bool:
    return os.environ.get("EXEC_ALLOW_NETWORK", "1") == "1"


@functools.cache
def _netns_prefix() -> tuple[str, ...]:
    """`unshare -rn` puts a program in its own network namespace with only loopback.

    Needs unprivileged user namespaces; many container hosts forbid them, so probe once.
    """
    if not POSIX or network_allowed():
        return ()
    unshare, ip = shutil.which("unshare"), shutil.which("ip")
    if not unshare or not ip:
        return ()
    prefix = (unshare, "-rn", "sh", "-c", f'{ip} link set lo up && exec "$@"', "sh")
    try:
        ok = subprocess.run([*prefix, "true"], capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    return prefix if ok else ()


def sandbox_report() -> dict:
    return {
        "network": "allowed" if network_allowed() else ("namespace" if _netns_prefix() else "guarded"),
        "limits": bool(POSIX and shutil.which("prlimit")),
        "parallel": _SLOTS._initial_value,  # type: ignore[attr-defined]
    }

LANGUAGE_LABELS = {
    "java": "Java", "python": "Python", "c": "C", "cpp": "C++", "javascript": "Node.js",
    "react": "React", "html": "HTML / CSS / JS", "matlab": "MATLAB", "sql": "SQL", "r": "R",
    "shell": "Shell", "other": "Other",
}
DEFAULT_NAMES = {
    "java": "Main.java", "python": "main.py", "c": "main.c", "cpp": "main.cpp", "javascript": "index.js",
    "react": "App.jsx", "html": "index.html", "matlab": "main.m", "sql": "queries.sql", "r": "main.R",
    "shell": "script.sh", "other": "main.txt",
}

DOCKER_IMAGES = {
    "java": os.environ.get("EXEC_IMAGE_JAVA", "eclipse-temurin:21-jdk"),
    "python": os.environ.get("EXEC_IMAGE_PYTHON", "labforge-python:latest"),
    "javascript": os.environ.get("EXEC_IMAGE_NODE", "node:22-slim"),
    "c": os.environ.get("EXEC_IMAGE_GCC", "gcc:14"),
    "cpp": os.environ.get("EXEC_IMAGE_GCC", "gcc:14"),
}

_SAFE_ENV = {
    "PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "JAVA_HOME",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "LANG", "LC_ALL",
}
_NODE_BUILTINS = {
    "assert", "buffer", "child_process", "crypto", "events", "fs", "http", "https", "os", "path",
    "process", "readline", "stream", "string_decoder", "timers", "url", "util", "zlib", "net",
    "worker_threads", "perf_hooks", "querystring", "dns", "cluster",
}


@dataclass
class _Proc:
    code: int
    output: str
    timed_out: bool
    ms: int


def find_chrome() -> str | None:
    env = os.environ.get("CHROME_PATH")
    if env and Path(env).exists():
        return env
    for name in ("chrome", "google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    ):
        if Path(candidate).exists():
            return candidate
    return None


def _bundled_python() -> str | None:
    """The project's runtime venv (.runtime/python): numpy, matplotlib, OpenCV, scikit-image."""
    base = ROOT / ".runtime" / "python"
    for exe in (base / "Scripts" / "python.exe", base / "bin" / "python"):
        if exe.exists():
            return str(exe)
    return None


def safe_rel(name: str, language: str) -> str:
    """A relative POSIX path that can't escape the work folder."""
    parts = [p for p in PurePosixPath((name or "").replace("\\", "/")).parts
             if p not in ("", ".", "..", "/") and not p.endswith(":")]
    parts = [re.sub(r"[^\w.\- ]", "_", p)[:60] for p in parts][-4:]
    return "/".join(parts) or DEFAULT_NAMES.get(language, "main.txt")


class CodeRunner:
    def __init__(self, timeout_seconds: int | None = None, backend: str | None = None):
        self.timeout = timeout_seconds or int(os.environ.get("LABFORGE_EXECUTION_TIMEOUT_SECONDS", "12"))
        self.backend = (backend or os.environ.get("EXEC_BACKEND", "local")).lower()
        self.python = os.environ.get("EXEC_PYTHON") or _bundled_python() or shutil.which("python") or sys.executable

    # ── capability report ──────────────────────────────────────────
    @functools.cached_property
    def _caps(self) -> dict[str, bool]:
        node = shutil.which("node") is not None
        if self.backend == "docker":
            docker = shutil.which("docker") is not None
            caps = {lang: docker for lang in DOCKER_IMAGES}
        else:
            caps = {
                "java": shutil.which("javac") is not None and shutil.which("java") is not None,
                "python": bool(self.python),
                "javascript": node,
                "c": shutil.which("gcc") is not None,
                "cpp": shutil.which("g++") is not None,
            }
        chrome = find_chrome() is not None
        caps["html"] = chrome
        caps["react"] = chrome and node and (NODE_RUNTIME / "esbuild").exists() and (NODE_RUNTIME / "react").exists()
        return caps

    def available(self) -> dict[str, bool]:
        return dict(self._caps)

    # ── entry point ────────────────────────────────────────────────
    def run(self, language: str, files: list[CodeFile], stdin: str, workdir: Path) -> RunResult:
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        language = (language or "other").lower()
        files = [CodeFile(name=safe_rel(f.name, language), code=f.code) for f in files if f.code.strip()]
        if not files:
            return RunResult(status="not_run", note="There's no code to run.")
        if not self._caps.get(language, False):
            label = LANGUAGE_LABELS.get(language, language)
            return RunResult(status="not_run", note=(
                f"{label} programs can't be run here. Run it on your machine and add a screenshot of the output."))
        if stdin and not stdin.endswith("\n"):
            stdin += "\n"
        try:
            return getattr(self, f"_run_{language}")(files, stdin, workdir)
        except OSError as exc:
            return RunResult(status="not_run", note=f"The runner couldn't start: {exc}")

    # ── languages ──────────────────────────────────────────────────
    def _run_java(self, files: list[CodeFile], stdin: str, wd: Path) -> RunResult:
        joined = "\n".join(f.code for f in files)
        if re.search(r"\bimport\s+javax?\.(swing|awt)\b|\bextends\s+(JFrame|Applet|Application)\b", joined):
            return RunResult(status="not_run", note=(
                "This program opens a window, so it can't be captured here. Add a screenshot of it."))
        sources: list[str] = []
        entry = None
        if len(files) == 1:
            code, entry, public = prepare_java(files[0].code)
            name = f"{public or entry}.java"
            (wd / name).write_text(code, encoding="utf-8")
            sources.append(name)
        else:
            for f in files:
                code = re.sub(r"^\s*package\s+[\w.]+\s*;\s*$", "", f.code, flags=re.MULTILINE)
                name = Path(f.name).name if f.name.endswith(".java") else f"{Path(f.name).stem}.java"
                (wd / name).write_text(code, encoding="utf-8")
                sources.append(name)
                if entry is None and re.search(r"\bstatic\s+(?:public\s+)?void\s+main\s*\(", code):
                    entry = prepare_java(code)[1]
            entry = entry or Path(sources[0]).stem
        shutil.copy(HARNESS / "LFLauncher.java", wd / "LFLauncher.java")
        comp = self._exec(["javac", "-encoding", "UTF-8", "-nowarn", *sources, "LFLauncher.java"],
                          wd, "", "java", timeout=max(self.timeout, 25))
        if comp.code != 0:
            missing = re.search(r"package ((?!java\.)[\w.]+) does not exist", comp.output)
            if missing:
                return RunResult(status="not_run", note=(
                    f"Needs the {missing.group(1)} library, which isn't installed here. "
                    "Add a screenshot of the output from your machine."))
            return RunResult(status="failed", output=_clip(comp.output), retryable=True,
                             note="The program didn't compile.")
        no_net = [] if network_allowed() else [
            f"-D{k}=127.0.0.1" for k in ("http.proxyHost", "https.proxyHost", "socksProxyHost")
        ] + [f"-D{k}=9" for k in ("http.proxyPort", "https.proxyPort", "socksProxyPort")]
        run = self._exec(["java", *no_net, "-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8", "-Dstderr.encoding=UTF-8",
                          "-Xss8m", "-cp", ".", "LFLauncher", entry], wd, stdin, "java")
        if "HeadlessException" in run.output:
            return RunResult(status="not_run", note="This program opens a window. Add a screenshot of it.")
        return self._result(run)

    def _run_python(self, files: list[CodeFile], stdin: str, wd: Path) -> RunResult:
        paths = self._write(files, wd)
        code = "\n".join(f.code for f in files)
        entry = _pick(paths, ("main.py", "app.py"), lambda p: "__main__" in (wd / p).read_text(encoding="utf-8"))
        shutil.copy(HARNESS / "lf_python.py", wd / "lf_python.py")
        flags = {
            "LF_NO_NET": "0" if network_allowed() else "1",
            "LF_MPL": "1" if "matplotlib" in code else "0",
            "LF_CV2": "1" if "cv2" in code else "0",
            "LF_PIL": "1" if re.search(r"\bfrom PIL\b|\bimport PIL\b", code) else "0",
        }
        exe = self.python if self.backend == "local" else "python"
        run = self._exec([exe, "-u", "lf_python.py", entry], wd, stdin, "python", extra_env=flags,
                         timeout=self.timeout + (8 if flags["LF_MPL"] == "1" or flags["LF_CV2"] == "1" else 0))
        missing = re.search(r"ModuleNotFoundError: No module named '([\w.]+)'", run.output)
        if missing:
            return RunResult(status="not_run", note=(
                f"Needs the {missing.group(1)} package, which isn't installed here. "
                "Add a screenshot of the output from your machine."))
        result = self._result(run)
        result.figures = sorted(str(p) for p in Path(wd / entry).parent.glob("figure_*.png"))
        return result

    def _run_javascript(self, files: list[CodeFile], stdin: str, wd: Path) -> RunResult:
        code = "\n".join(f.code for f in files if not f.name.endswith(".json"))
        if re.search(r"\bdocument\.|\bwindow\.", code) and not re.search(r"require\(|^\s*import\s", code, re.M):
            return RunResult(status="not_run", note="This script runs in a browser page. Add a screenshot of it.")
        missing = _missing_node_packages(code)
        if missing:
            return RunResult(status="not_run", note=(
                f"Needs npm packages that aren't installed here ({', '.join(missing)}). "
                "Run it on your machine and add a screenshot."))
        paths = self._write([f for f in files if Path(f.name).name != "package-lock.json"], wd)
        js = [p for p in paths if p.endswith((".js", ".mjs", ".cjs"))]
        if not js:
            return RunResult(status="not_run", note="There's no JavaScript file to run.")
        entry = _pick(js, ("index.js", "server.js", "app.js", "main.js"), lambda p: "listen(" in (wd / p).read_text(encoding="utf-8"))
        _link_node_modules(wd)
        cmd = ["node", entry]
        timeout = self.timeout
        if re.search(r"\bmongoose\b|\bmongodb\b", code):
            if not _mongod():
                return RunResult(status="not_run", note=(
                    "Needs a MongoDB server, which isn't set up here. Run it on your machine and add a screenshot."))
            shutil.copy(HARNESS / "lf_mongo.cjs", wd / "lf_mongo.cjs")
            cmd = ["node", "lf_mongo.cjs", entry]
            timeout += 25
        # NODE_NO_WARNINGS: library deprecation notices aren't part of the program's output.
        node_env = {"NODE_PATH": str(NODE_RUNTIME), "NODE_ENV": "development", "NODE_NO_WARNINGS": "1"}
        if not network_allowed():
            # NODE_OPTIONS also reaches the child that lf_mongo.cjs starts.
            node_env["NODE_OPTIONS"] = f'--require "{(HARNESS / "lf_nonet.cjs").as_posix()}"'  # quotes: backslashes are escapes
        run = self._exec(cmd, wd, stdin, "javascript", timeout=timeout, extra_env=node_env)
        if run.timed_out and re.search(r"listen\(", code):
            return RunResult(status="failed", output=_clip(run.output), retryable=True, note=(
                "The server kept running. It should call its own routes, print the responses and close."))
        return self._result(run)

    def _run_react(self, files: list[CodeFile], stdin: str, wd: Path) -> RunResult:
        code = "\n".join(f.code for f in files)
        missing = _missing_node_packages(code, extra_ok={"react", "react-dom", "react-router-dom", "axios"})
        if missing:
            return RunResult(status="not_run", note=(
                f"Needs npm packages that aren't installed here ({', '.join(missing)}). Add a screenshot of the app."))
        src = wd / "src"
        paths = self._write([f for f in files if not f.name.endswith(("index.html", "package.json",
                                                                       "package-lock.json", "vite.config.js"))], src)
        names = {Path(p).name.lower(): p for p in paths}
        entry = next((names[n] for n in ("main.jsx", "index.jsx", "main.js", "index.js", "main.tsx") if n in names), None)
        if entry is None:
            app = next((p for p in paths if Path(p).stem.lower() == "app"), paths[0])
            rel = "./" + str(PurePosixPath(app).with_suffix(""))
            (src / "__entry.jsx").write_text(
                "import { createRoot } from 'react-dom/client';\n"
                f"import App from '{rel}';\n"
                "createRoot(document.getElementById('root')).render(<App />);\n", encoding="utf-8")
            entry = "__entry.jsx"
        shutil.copy(HARNESS / "lf_react_build.cjs", wd / "lf_react_build.cjs")
        build = _run_process(["node", "lf_react_build.cjs", f"src/{entry}"], wd, "", 60,
                             _clean_env(wd, {"LF_NODE_MODULES": str(NODE_RUNTIME), "NODE_PATH": str(NODE_RUNTIME)}))
        if build.code != 0 or not (wd / "dist" / "app.js").exists():
            return RunResult(status="failed", output=_clip(build.output), retryable=True,
                             note="The React code didn't build.")
        return self._screenshot(wd / "dist", "", wd)  # "/" so React Router's "/" route matches

    def _run_html(self, files: list[CodeFile], stdin: str, wd: Path) -> RunResult:
        site = wd / "site"
        paths = self._write(files, site)
        pages = [p for p in paths if p.endswith((".html", ".htm"))]
        if not pages:
            return RunResult(status="not_run", note="There's no HTML page to open.")
        entry = next((p for p in pages if Path(p).name.lower() == "index.html"), pages[0])
        return self._screenshot(site, entry, wd)

    def _run_c(self, files: list[CodeFile], stdin: str, wd: Path) -> RunResult:
        return self._run_native(files, stdin, wd, "c", "gcc", (".c",), ["-lm"])

    def _run_cpp(self, files: list[CodeFile], stdin: str, wd: Path) -> RunResult:
        return self._run_native(files, stdin, wd, "cpp", "g++", (".cpp", ".cc", ".cxx"), ["-std=c++17", "-O2"])

    def _run_native(self, files, stdin, wd, lang, compiler, exts, flags) -> RunResult:
        paths = self._write(files, wd)
        sources = [p for p in paths if p.endswith(exts)] or paths[:1]
        exe = "a.exe" if os.name == "nt" and self.backend == "local" else "a.out"
        comp = self._exec([compiler, *sources, "-o", exe, *flags], wd, "", lang, timeout=max(self.timeout, 25))
        if comp.code != 0:
            return RunResult(status="failed", output=_clip(comp.output), retryable=True,
                             note="The program didn't compile.")
        cmd = [str(wd / exe)] if self.backend == "local" else ["./" + exe]
        return self._result(self._exec(cmd, wd, stdin, lang))

    # ── screenshots of pages ───────────────────────────────────────
    def _screenshot(self, site: Path, entry: str, wd: Path) -> RunResult:
        chrome = find_chrome()
        shot = wd / "figure_01.png"
        # Chrome puts a unix socket in its profile folder; job paths are too long for that (108 chars).
        profile = Path(tempfile.mkdtemp(prefix="lfc-")) if POSIX else wd / ".chrome"
        with _StaticServer(site) as port:
            url = f"http://127.0.0.1:{port}/{entry}"
            cmd = [
                chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                "--no-default-browser-check", "--disable-extensions", "--mute-audio",
                f"--user-data-dir={profile}", "--window-size=1280,860",
                # Containers: no user namespaces for Chrome's sandbox, and a tiny /dev/shm.
                *(["--no-sandbox", "--disable-dev-shm-usage"] if os.environ.get("CHROME_NO_SANDBOX") == "1" else []),
                "--virtual-time-budget=4000", f"--screenshot={shot}",
            ]
            if os.environ.get("HTML_ALLOW_NETWORK") != "1":
                # Only our own static server is reachable; everything else hits a dead proxy.
                cmd += ["--proxy-server=http://127.0.0.1:9", f"--proxy-bypass-list=<-loopback>;127.0.0.1:{port}"]
            cmd.append(url)
            # Chrome also keeps its singleton socket under TMPDIR, so that has to be short too.
            short_tmp = {k: str(profile) for k in ("TMPDIR", "TMP", "TEMP")} if POSIX else {}
            proc = _run_process(cmd, wd, "", 30, _clean_env(wd, short_tmp))
        shutil.rmtree(profile, ignore_errors=True)
        if not shot.exists():
            return RunResult(status="failed", note="The page couldn't be rendered.", output=_clip(proc.output))
        _trim_page_screenshot(shot)
        return RunResult(status="passed", figures=[str(shot)], note="Screenshot taken in Chrome at 1280 px wide.")

    # ── plumbing ───────────────────────────────────────────────────
    @staticmethod
    def _write(files: list[CodeFile], base: Path) -> list[str]:
        written = []
        for f in files:
            target = base / f.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f.code, encoding="utf-8")
            written.append(f.name)
        return written

    def _exec(self, cmd: list[str], wd: Path, stdin: str, lang: str,
              timeout: int | None = None, extra_env: dict | None = None) -> _Proc:
        timeout = timeout or self.timeout
        env = _clean_env(wd, extra_env or {})
        if self.backend == "docker" and lang in DOCKER_IMAGES:
            env_args: list[str] = []
            for key in ("PYTHONIOENCODING", "PYTHONUTF8", *(k for k in (extra_env or {}) if k != "NODE_PATH")):
                env_args += ["-e", f"{key}={env[key]}"]
            cmd = [
                "docker", "run", "--rm", "-i", "--network", "none", "--memory", "384m", "--cpus", "1",
                "--pids-limit", "128", "--security-opt", "no-new-privileges", "--cap-drop", "ALL",
                "-v", f"{wd.resolve()}:/work", "-w", "/work", *env_args, DOCKER_IMAGES[lang], *cmd,
            ]
            timeout += 15  # container start-up
        elif self.backend == "local":
            cmd = [*_netns_prefix(), *cmd]
        return _run_process(cmd, wd, stdin, timeout, env)

    def _result(self, proc: _Proc) -> RunResult:
        output = _clip(proc.output)
        if proc.timed_out:
            return RunResult(status="failed", output=output, retryable=True, note=(
                "It didn't finish in time. If it waits for input, add more lines under Input."))
        if proc.code != 0:
            return RunResult(status="failed", output=output, retryable=True,
                             note=f"The program stopped with an error (exit code {proc.code}).")
        return RunResult(status="passed", output=output)


def prepare_java(code: str) -> tuple[str, str, str | None]:
    """Strip package lines and make sure only the entry class is public.

    Returns (code, entry class name, public class name or None).
    """
    code = re.sub(r"^\s*package\s+[\w.]+\s*;\s*$", "", code, flags=re.MULTILINE).strip() + "\n"
    classes = [(m.start(), m.group(1)) for m in
               re.finditer(r"\b(?:class|record|enum|interface)\s+([A-Z_a-z]\w*)", code)]
    main_at = re.search(r"\bstatic\s+(?:public\s+)?void\s+main\s*\(", code)
    entry = None
    if main_at:
        before = [name for pos, name in classes if pos < main_at.start()]
        entry = before[-1] if before else None
    if not entry:
        entry = classes[0][1] if classes else "Main"
    publics = re.findall(r"^public\s+(?:final\s+|abstract\s+)*(?:class|record|enum|interface)\s+(\w+)",
                         code, re.MULTILINE)
    for name in publics:
        if name != entry:
            code = re.sub(rf"^public\s+((?:final\s+|abstract\s+)*(?:class|record|enum|interface)\s+{name}\b)",
                          r"\1", code, count=1, flags=re.MULTILINE)
    if entry in publics:
        code = re.sub(rf"^(public\s+)abstract\s+(class\s+{entry}\b)", r"\1\2", code, flags=re.MULTILINE)
    public = entry if entry in publics else None
    return code, entry, public


def _pick(paths: list[str], preferred: tuple[str, ...], fallback_test) -> str:
    by_name = {Path(p).name.lower(): p for p in paths}
    for name in preferred:
        if name in by_name:
            return by_name[name]
    for p in paths:
        try:
            if fallback_test(p):
                return p
        except OSError:
            continue
    return paths[0]


def _missing_node_packages(code: str, extra_ok: set[str] | None = None) -> list[str]:
    found = set(re.findall(r"require\(\s*['\"]([^'\"./][^'\"]*)['\"]\s*\)", code))
    found |= set(re.findall(r"^\s*import\s[^'\"]*?['\"]([^'\"./][^'\"]*)['\"]", code, re.MULTILINE))
    found |= set(re.findall(r"^\s*import\s+['\"]([^'\"./][^'\"]*)['\"]", code, re.MULTILINE))
    missing = []
    for spec in sorted(found):
        spec = spec.removeprefix("node:")
        pkg = "/".join(spec.split("/")[:2]) if spec.startswith("@") else spec.split("/")[0]
        if pkg in _NODE_BUILTINS or (extra_ok and pkg in extra_ok):
            continue
        if not (NODE_RUNTIME / pkg).exists():
            missing.append(pkg)
    return missing


def _link_node_modules(wd: Path) -> None:
    """Expose the runtime packages to ES-module imports, which ignore NODE_PATH."""
    link = wd / "node_modules"
    if link.exists() or not NODE_RUNTIME.exists():
        return
    try:
        if os.name == "nt":
            import _winapi

            _winapi.CreateJunction(str(NODE_RUNTIME), str(link))
        else:
            link.symlink_to(NODE_RUNTIME, target_is_directory=True)
    except OSError:
        pass


def unlink_node_modules(wd: Path) -> None:
    """Remove the junction before deleting a work folder, so the runtime survives."""
    link = Path(wd) / "node_modules"
    try:
        if link.is_symlink() or (os.name == "nt" and link.exists() and os.path.isjunction(link)):
            os.unlink(link) if os.name != "nt" else os.rmdir(link)
    except OSError:
        pass


def _mongod() -> Path | None:
    env = os.environ.get("EXEC_MONGOD")
    if env and Path(env).exists():
        return Path(env)
    for name in ("mongod.exe", "mongod"):
        candidate = ROOT / ".runtime" / "mongodb" / name
        if candidate.exists():
            return candidate
    return None


_MPL_CACHE = ROOT / ".runtime" / "mplconfig"  # font cache survives between runs (saves ~15 s)
_NOISE = re.compile(r"^Matplotlib is building the font cache.*\n?", re.MULTILINE)


def _clean_env(wd: Path, extra: dict) -> dict:
    """Child processes get a minimal environment: no API keys, no secrets."""
    env = {k: v for k, v in os.environ.items() if k.upper() in _SAFE_ENV}
    tmp = str(wd.resolve())
    env.update({
        "TEMP": tmp, "TMP": tmp, "TMPDIR": tmp, "HOME": tmp, "USERPROFILE": tmp,
        "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "MPLCONFIGDIR": str(_MPL_CACHE), "NO_COLOR": "1",
    })
    mongod = _mongod()
    if mongod:
        env["MONGOMS_SYSTEM_BINARY"] = str(mongod)
        env["MONGOMS_VERSION"] = (mongod.parent / "VERSION").read_text().strip() if (mongod.parent / "VERSION").exists() else ""
        env["MONGOMS_DISABLE_POSTINSTALL"] = "1"
    env.update(extra)
    return env


def _run_process(cmd: list[str], wd: Path, stdin: str, timeout: int, env: dict) -> _Proc:
    flags = 0 if POSIX else subprocess.CREATE_NO_WINDOW
    if not POSIX and cmd and not Path(cmd[0]).is_absolute():
        cmd = [shutil.which(cmd[0], path=env.get("PATH")) or cmd[0], *cmd[1:]]
    prlimit = shutil.which("prlimit") if POSIX else None
    if prlimit:
        # No core dumps, no file over 1 GB (MongoDB preallocates ~100 MB journals), and a
        # CPU-seconds ceiling (threads count, so be generous).
        cmd = [prlimit, "--core=0", f"--fsize={1 << 30}", f"--cpu={timeout * 4 + 10}", "--", *cmd]
    with _SLOTS:
        start = time.monotonic()
        proc = subprocess.Popen(
            cmd, cwd=wd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=env, creationflags=flags, start_new_session=POSIX,
        )
        try:
            out, _ = proc.communicate(stdin.encode("utf-8"), timeout=timeout)
            code, timed_out = proc.returncode, False
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            try:
                out, _ = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                out = b""
            code, timed_out = -1, True
        finally:
            if POSIX:
                _kill_tree(proc)  # anything the program left running in the background
        elapsed = int((time.monotonic() - start) * 1000)
    text = (out or b"").decode("utf-8", errors="replace").replace("\r\n", "\n")
    text = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text)  # strip colour codes
    text = _NOISE.sub("", text)
    return _Proc(code, text, timed_out, elapsed)


def _kill_tree(proc: subprocess.Popen) -> None:
    if POSIX:
        import signal

        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    elif proc.poll() is None:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        proc.kill()
    except OSError:
        pass


def _clip(text: str) -> str:
    text = text.rstrip()
    if len(text) > MAX_OUTPUT_CHARS:
        text = text[:MAX_OUTPUT_CHARS] + "\n… output cut off"
    return text


def _trim_page_screenshot(path: Path) -> None:
    """Crop empty space below the page content so the report image isn't mostly blank."""
    from PIL import Image, ImageChops

    with Image.open(path) as img:
        rgb = img.convert("RGB")
    bg = Image.new("RGB", rgb.size, rgb.getpixel((rgb.width - 1, rgb.height - 1)))
    box = ImageChops.difference(rgb, bg).getbbox()
    if box:
        bottom = min(rgb.height, max(box[3] + 32, 240))
        rgb = rgb.crop((0, 0, rgb.width, bottom))
    rgb.save(path, optimize=True)


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D401 - silence request logs
        pass

    def send_head(self):
        # Single-page apps: unknown paths without an extension get index.html.
        path = self.translate_path(self.path)
        if not os.path.exists(path) and "." not in Path(self.path.split("?")[0]).name:
            self.path = "/index.html"
        return super().send_head()


class _StaticServer:
    def __init__(self, root: Path):
        self.root = root

    def __enter__(self) -> int:
        handler = functools.partial(_QuietHandler, directory=str(self.root))
        self.httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self.httpd.server_address[1]

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
