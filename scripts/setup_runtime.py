"""Install the packages student programs may use, into .runtime/ (not the app's venv).

    python scripts/setup_runtime.py            # Python libs + Node packages
    python scripts/setup_runtime.py --mongo    # also fetch a MongoDB server binary

Python: numpy, matplotlib, pillow, opencv-python-headless, scikit-image, pandas
Node:   react, react-dom, react-router-dom, esbuild, express, mongoose, bcryptjs,
        jsonwebtoken, cors, uuid, axios, dotenv, body-parser, morgan, express-validator,
        mongodb-memory-server
MongoDB: only mongod is kept from the official archive. The runner points
mongodb-memory-server at it, so Mongoose experiments run against a throwaway
database.
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
        url = f"https://fastdl.mongodb.org/linux/mongodb-linux-x86_64-ubuntu2204-{MONGO_VERSION}.tgz"
    archive = RUNTIME / "mongodb" / Path(url).name
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        print(f"Downloading {url} (large on Windows; only mongod is kept)…")
        tmp = archive.with_suffix(".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.replace(archive)
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mongo", action="store_true", help="also download a MongoDB server binary")
    parser.add_argument("--only-mongo", action="store_true")
    args = parser.parse_args()
    if not args.only_mongo:
        python_runtime()
        node_runtime()
    if args.mongo or args.only_mongo:
        print("mongod:", mongo())
    print("Runtime ready in", RUNTIME)
