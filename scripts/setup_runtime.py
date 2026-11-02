"""Install the packages student programs may use, into .runtime/ (not the app's venv).

    python scripts/setup_runtime.py            # Python libs + Node packages
    python scripts/setup_runtime.py --mongo    # also fetch a MongoDB server binary
    python scripts/setup_runtime.py --spring   # also fetch Spring Boot jars (needs a JDK)

Python: numpy, matplotlib, pillow, opencv-python-headless, scikit-image, pandas
Node:   react, react-dom, react-router-dom, esbuild, express, mongoose, bcryptjs,
        jsonwebtoken, cors, uuid, axios, dotenv, body-parser, morgan, express-validator,
        mongodb-memory-server
MongoDB: only mongod is kept from the official archive. The runner points
mongodb-memory-server at it, so Mongoose experiments run against a throwaway
database.
Spring:  Spring Boot (web, data-jpa, validation) and H2 jars in .runtime/java/spring, resolved
with Maven (downloaded for the occasion when it isn't installed, then removed).
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime"
PY_PACKAGES = ["numpy", "matplotlib", "pillow", "opencv-python-headless", "scikit-image", "pandas"]
NODE_PACKAGES = [
    "react@18", "react-dom@18", "react-router-dom@6", "esbuild", "express", "mongoose", "bcryptjs",
    "jsonwebtoken", "cors", "uuid", "axios", "dotenv", "body-parser", "morgan", "express-validator",
    "mongodb-memory-server-core",
]
MONGO_VERSION = "8.0.4"
SPRING_BOOT_VERSION = "3.5.16"
MAVEN_VERSION = "3.9.16"
SPRING_POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>{version}</version>
  </parent>
  <groupId>labforge</groupId>
  <artifactId>spring-runtime</artifactId>
  <version>1</version>
  <dependencies>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-web</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-data-jpa</artifactId></dependency>
    <dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-validation</artifactId></dependency>
    <dependency><groupId>com.h2database</groupId><artifactId>h2</artifactId></dependency>
  </dependencies>
</project>
"""


def python_runtime() -> None:
    venv = RUNTIME / "python"
    if not venv.exists():
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    exe = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    subprocess.check_call([str(exe), "-m", "pip", "install", "-q", "--disable-pip-version-check", *PY_PACKAGES])
    (RUNTIME / "mplconfig").mkdir(parents=True, exist_ok=True)


def node_runtime() -> None:
    node_dir = RUNTIME / "node"
    node_dir.mkdir(parents=True, exist_ok=True)
    pkg = node_dir / "package.json"
    if not pkg.exists():
        pkg.write_text(json.dumps({"name": "labforge-runtime", "private": True}, indent=2))
    npm = shutil.which("npm") or "npm"
    # mongodb-memory-server-core has no postinstall download; the binary comes from mongo().
    subprocess.check_call([npm, "install", "--no-audit", "--no-fund", "--loglevel=error", *NODE_PACKAGES],
                          cwd=node_dir, shell=sys.platform == "win32")


def download(url: str, dest: Path) -> None:
    """Download to dest via dest.part, resuming a partial file if the server allows it."""
    tmp = dest.with_name(dest.name + ".part")
    legacy = dest.with_suffix(".part")  # name used by older versions of this script
    if legacy.exists() and not tmp.exists():
        legacy.replace(tmp)
    have = tmp.stat().st_size if tmp.exists() else 0
    req = urllib.request.Request(url, headers={"Range": f"bytes={have}-"} if have else {})
    with urllib.request.urlopen(req, timeout=60) as resp:
        resumed = have and resp.status == 206
        total = int(resp.headers.get("Content-Length") or 0) + (have if resumed else 0)
        if have and not resumed:
            have = 0
        done = have
        last = -1
        with tmp.open("ab" if resumed else "wb") as out:
            while chunk := resp.read(1 << 20):
                out.write(chunk)
                done += len(chunk)
                pct = int(done * 100 / total) if total else 0
                if pct // 10 != last:
                    last = pct // 10
                    print(f"  {done >> 20} / {total >> 20} MB", flush=True)
    if total and tmp.stat().st_size != total:
        raise RuntimeError(f"download incomplete ({tmp.stat().st_size} of {total} bytes); run again to resume")
    tmp.replace(dest)


def linux_build() -> str:
    """MongoDB publishes per-distro builds; Debian 12 images need the debian12 one."""
    try:
        info = dict(line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines() if "=" in line)
    except OSError:
        return "ubuntu2204"
    distro, version = info.get("ID", "").strip('"'), info.get("VERSION_ID", "").strip('"')
    if distro == "debian" and version.startswith("12"):
        return "debian12"
    if distro == "ubuntu" and version.startswith("24"):
        return "ubuntu2404"
    return "ubuntu2204"


def mongo() -> Path:
    system = platform.system()
    target = RUNTIME / "mongodb" / ("mongod.exe" if system == "Windows" else "mongod")
    if target.exists():
        return target
    if system == "Windows":
        url = f"https://fastdl.mongodb.org/windows/mongodb-windows-x86_64-{MONGO_VERSION}.zip"
    elif system == "Darwin":
        arch = "arm64" if platform.machine() == "arm64" else "x86_64"
        url = f"https://fastdl.mongodb.org/osx/mongodb-macos-{arch}-{MONGO_VERSION}.tgz"
    else:
        url = f"https://fastdl.mongodb.org/linux/mongodb-linux-x86_64-{linux_build()}-{MONGO_VERSION}.tgz"
    archive = RUNTIME / "mongodb" / Path(url).name
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        print(f"Downloading {url} (large on Windows; only mongod is kept)…")
        download(url, archive)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as zf:
            name = next(n for n in zf.namelist() if n.endswith("/bin/mongod.exe"))
            with zf.open(name) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    else:
        with tarfile.open(archive) as tf:
            member = next(m for m in tf.getmembers() if m.name.endswith("/bin/mongod"))
            with tf.extractfile(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
        target.chmod(0o755)
    archive.unlink()
    (target.parent / "VERSION").write_text(MONGO_VERSION)
    return target


def spring() -> Path:
    """Spring Boot + H2 jars for Java programs that import org.springframework / jakarta."""
    target = RUNTIME / "java" / "spring"
    if (target / "VERSION").exists() and (target / "VERSION").read_text().strip() == SPRING_BOOT_VERSION:
        return target
    work = RUNTIME / "java" / "build"
    work.mkdir(parents=True, exist_ok=True)
    (work / "pom.xml").write_text(SPRING_POM.format(version=SPRING_BOOT_VERSION), encoding="utf-8")
    mvn = shutil.which("mvn")
    if not mvn:
        base = f"https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/{MAVEN_VERSION}"
        archive = work / f"apache-maven-{MAVEN_VERSION}-bin.zip"
        if not archive.exists():
            print("Downloading Maven…")
            download(f"{base}/{archive.name}", archive)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(work)
        home = work / f"apache-maven-{MAVEN_VERSION}"
        mvn = str(home / "bin" / ("mvn.cmd" if sys.platform == "win32" else "mvn"))
        if sys.platform != "win32":
            Path(mvn).chmod(0o755)
    shutil.rmtree(target, ignore_errors=True)
    subprocess.check_call([mvn, "-q", "-B", f"-Dmaven.repo.local={work / 'm2'}", "dependency:copy-dependencies",
                           f"-DoutputDirectory={target}", "-DincludeScope=runtime"],
                          cwd=work, shell=sys.platform == "win32")
    shutil.rmtree(work, ignore_errors=True)
    (target / "VERSION").write_text(SPRING_BOOT_VERSION)
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mongo", action="store_true", help="also download a MongoDB server binary")
    parser.add_argument("--only-mongo", action="store_true")
    parser.add_argument("--spring", action="store_true", help="also fetch Spring Boot jars (needs a JDK)")
    parser.add_argument("--only-spring", action="store_true")
    args = parser.parse_args()
    if not (args.only_mongo or args.only_spring):
        python_runtime()
        node_runtime()
    if args.mongo or args.only_mongo:
        print("mongod:", mongo())
    if args.spring or args.only_spring:
        print("spring:", spring())
    print("Runtime ready in", RUNTIME)
