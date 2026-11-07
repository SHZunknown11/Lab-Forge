"""Runs a .sql script against an in-memory SQLite database and prints it like a console session."""
import sqlite3
import sys

src = open(sys.argv[1], encoding="utf-8").read()
db = sqlite3.connect(":memory:")


def show(cols, rows):
    cells = [[("NULL" if v is None else str(v)) for v in r] for r in rows]
    widths = [max([len(str(c))] + [len(r[i]) for r in cells]) for i, c in enumerate(cols)]
    bar = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def line(vals):
        return "| " + " | ".join(v.ljust(w) for v, w in zip(vals, widths)) + " |"

    print(bar)
    print(line([str(c) for c in cols]))
    print(bar)
    for r in cells:
        print(line(r))
    print(bar)
    print(f"{len(cells)} row{'s' if len(cells) != 1 else ''} in set")


buf = ""
failed = False
for raw in src.splitlines(keepends=True):
    if not buf and raw.lstrip().startswith(("--", "#")):
        continue
    buf += raw
    if not sqlite3.complete_statement(buf):
        continue
    stmt, buf = buf.strip(), ""
    try:
        cur = db.execute(stmt)
        if cur.description:
            show([d[0] for d in cur.description], cur.fetchall())
        else:
            print(f"Query OK, {max(cur.rowcount, 0)} row{'s' if cur.rowcount != 1 else ''} affected")
        print()
    except sqlite3.Error as exc:
        print(f"ERROR: {exc}\n  in: {stmt.splitlines()[0][:100]}")
        failed = True
        break
if buf.strip() and not failed:
    print("ERROR: the last statement is missing its semicolon")
    failed = True
sys.exit(1 if failed else 0)
