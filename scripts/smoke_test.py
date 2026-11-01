"""End-to-end check of a running LabForge server through its HTTP API.

    python scripts/smoke_test.py http://127.0.0.1:7860            # every runtime, no AI call
    python scripts/smoke_test.py https://you-labforge.hf.space --ai # plus one real AI draft

Uploads a sheet that already contains its code (served offline or from the cache),
runs one program per runtime (Java, Python + matplotlib, OpenCV, C, Node, Express,
Mongoose, React, HTML), then renders the report to Word and PDF. Exits 1 on any failure.
Uses only the standard library so it runs anywhere.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
import uuid

SHEET = """Experiment 1.1
Aim: To print a greeting and the square of a number in Java.
Objective: Use Scanner for input and print formatted output.
Easy Level
Problem Statement: Read a number and print its square.
Code:
import java.util.Scanner;
public class Square {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        System.out.print("Enter a number: ");
        int n = sc.nextInt();
        System.out.println("Square: " + (n * n));
    }
}
"""

PROGRAMS = {
    "python + matplotlib": ("python", [("main.py", (
        "import matplotlib.pyplot as plt\n"
        "xs = list(range(6))\n"
        "plt.plot(xs, [x * x for x in xs]); plt.title('squares'); plt.show()\n"
        "print('plotted', len(xs), 'points')\n"))], "", "plotted 6 points", True),
    "python + opencv": ("python", [("main.py", (
        "import cv2, numpy as np\n"
        "img = np.zeros((60, 80, 3), np.uint8); img[:, :40] = 255\n"
        "edges = cv2.Canny(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 50, 150)\n"
        "print('edge pixels:', int((edges > 0).sum()))\n"
        "cv2.imshow('edges', edges); cv2.waitKey(0)\n"))], "", "edge pixels:", True),
    "python input": ("python", [("main.py", "n = int(input('n: '))\nprint('double', n * 2)\n")],
                     "21", "n: 21\ndouble 42", False),
    "c": ("c", [("main.c", '#include <stdio.h>\nint main(){int a;scanf("%d",&a);printf("cube %d\\n",a*a*a);return 0;}\n')],
          "3", "cube 27", False),
    "node": ("javascript", [("index.js", "console.log([3,1,2].sort().join(','));\n")], "", "1,2,3", False),
    "express": ("javascript", [("server.js", (
        "const express = require('express');\n"
        "const app = express();\n"
        "app.get('/hi', (req, res) => res.json({ ok: true }));\n"
        "const srv = app.listen(0, async () => {\n"
        "  const r = await fetch(`http://127.0.0.1:${srv.address().port}/hi`);\n"
        "  console.log('GET /hi ->', r.status, JSON.stringify(await r.json()));\n"
        "  srv.close();\n"
        "});\n"))], "", 'GET /hi -> 200 {"ok":true}', False),
    "mongoose": ("javascript", [("index.js", (
        "const mongoose = require('mongoose');\n"
        "(async () => {\n"
        "  await mongoose.connect(process.env.MONGO_URI);\n"
        "  const S = mongoose.model('S', new mongoose.Schema({ name: { type: String, required: true } }));\n"
        "  await S.create([{ name: 'A' }, { name: 'B' }]);\n"
        "  console.log('students:', await S.countDocuments());\n"
        "  await mongoose.disconnect();\n"
        "})();\n"))], "", "students: 2", False),
    "react": ("react", [("App.jsx", (
        "import { useState } from 'react';\n"
        "export default function App() {\n"
        "  const [n] = useState(3);\n"
        "  return <main style={{ padding: 24 }}><h1>Counter</h1><p>Count: {n}</p></main>;\n"
        "}\n"))], "", None, True),
    "html": ("html", [("index.html", "<!doctype html><h1>Hello lab</h1><p>Static page.</p>")], "", None, True),
    "internet blocked": ("python", [("main.py", (
        "import urllib.request\n"
        "try:\n"
        "    urllib.request.urlopen('http://example.com', timeout=3)\n"
        "    print('online')\n"
        "except Exception as e:\n"
        "    print('offline')\n"))], "", "offline", False),
}


class Smoke:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.failures: list[str] = []

    def call(self, method: str, path: str, body: bytes | None = None, headers: dict | None = None,
             timeout: float = 180) -> tuple[int, bytes]:
        req = urllib.request.Request(self.base + path, data=body, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def json(self, method: str, path: str, payload: dict | None = None):
        body = json.dumps(payload).encode() if payload is not None else None
        status, data = self.call(method, path, body, {"Content-Type": "application/json"} if body else {})
        return status, (json.loads(data) if data and data[:1] in b"{[" else data)

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")
        if not ok:
            self.failures.append(name)
        return ok

    def draft(self, sheet: str, subject: str, fresh: bool = False) -> tuple[str, dict | None, list]:
        boundary = uuid.uuid4().hex
        parts = []
        for key, value in (("text", sheet), ("language", "auto"), ("subject", subject),
                           ("fresh", "true" if fresh else "false")):
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n')
        body = ("".join(parts) + f"--{boundary}--\r\n").encode()
        status, data = self.call("POST", "/api/drafts", body,
                                 {"Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=300)
        if status != 200:
            return "", None, [{"type": "error", "message": f"HTTP {status}: {data[:200]!r}"}]
        events = [json.loads(line) for line in data.decode().splitlines() if line.strip()]
        job = events[0].get("job", "")
        done = next((e for e in events if e["type"] == "done"), None)
        return job, (done or {}).get("draft"), events

    def run(self, ai: bool) -> int:
        print(f"LabForge smoke test against {self.base}")
        status, _ = self.json("GET", "/api/health")
        self.check("health", status == 200)
        status, meta = self.json("GET", "/api/meta")
        self.check("meta", status == 200 and isinstance(meta, dict))
        if isinstance(meta, dict):
            runnable = sorted(lang["id"] for lang in meta.get("languages", []) if lang.get("runnable"))
            print(f"       runnable: {', '.join(runnable)}; pdf: {meta.get('pdf')}; ai: {meta.get('ai_ready')}")

        t = time.time()
        job, draft, events = self.draft(SHEET, "Project Based Learning in Java")
        errors = [e["message"] for e in events if e["type"] == "error"]
        ok = draft is not None and draft["tasks"] and draft["tasks"][0]["status"] == "passed"
        self.check("sheet with code -> draft, Java run", bool(ok),
                   errors[0] if errors else f"{time.time() - t:.1f}s")
        if not job or draft is None:
            return self.finish()

        for name, (lang, files, stdin, expect, wants_image) in PROGRAMS.items():
            task = {"title": name, "language": lang, "stdin": stdin,
                    "files": [{"name": n, "code": c} for n, c in files]}
            t = time.time()
            status, res = self.json("POST", f"/api/jobs/{job}/run", {"index": 1, "task": task})
            if status != 200:
                self.check(name, False, f"HTTP {status}")
                continue
            passed = res["status"] == "passed"
            text_ok = expect is None or expect in res.get("output", "")
            image_ok = not wants_image or bool(res.get("images"))
            detail = f"{time.time() - t:.1f}s"
            if not (passed and text_ok and image_ok):
                detail += f" status={res['status']} note={res.get('note', '')[:120]!r} out={res.get('output', '')[:160]!r}"
            self.check(name, passed and text_ok and image_ok, detail)

        fields = [{"label": "Student Name", "value": "Smoke Test"}, {"label": "UID", "value": "24BCS00000"},
                  {"label": "Subject Name", "value": "Project Based Learning in Java"}]
        t = time.time()
        status, res = self.json("POST", f"/api/jobs/{job}/render",
                                {"draft": draft, "fields": fields, "template": "cu-cse", "pdf": True})
        if self.check("render", status == 200 and bool(res.get("docx")), f"{time.time() - t:.1f}s"):
            for key in ("docx", "pdf"):
                if not res.get(key):
                    self.check(f"download {key}", False, res.get("pdf_error", "missing"))
                    continue
                code, data = self.call("GET", f"/api/jobs/{job}/files/{res['render']}/{res[key]}")
                magic = b"PK" if key == "docx" else b"%PDF-"
                self.check(f"download {key}", code == 200 and data.startswith(magic), f"{len(data) // 1024} KB")

        if ai:
            t = time.time()
            sheet = ("Experiment 9.9 (smoke test " + uuid.uuid4().hex[:6] + ")\n"
                     "Aim: Write a Python program that reads N and prints the first N Fibonacci numbers.\n"
                     "Objective: Practise loops and input handling.")
            _, draft, events = self.draft(sheet, "Competitive Coding")
            errors = [e["message"] for e in events if e["type"] == "error"]
            ok = draft is not None and all(task["status"] == "passed" for task in draft["tasks"])
            self.check("AI draft (real provider)", ok, errors[0] if errors else f"{time.time() - t:.1f}s")
        return self.finish()

    def finish(self) -> int:
        if self.failures:
            print(f"FAILED: {', '.join(self.failures)}")
            return 1
        print("All checks passed.")
        return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(Smoke(args[0] if args else "http://127.0.0.1:7860").run(ai="--ai" in sys.argv))
