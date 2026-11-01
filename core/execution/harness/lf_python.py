"""Runs a student's Python script so the captured run matches a real terminal.

- input() echoes what was typed, the way a terminal shows it.
- matplotlib figures, cv2.imshow and PIL Image.show are saved as PNGs in the
  working folder instead of opening windows, so they can go into the report.
- Tracebacks hide this wrapper's frames.
"""
import builtins
import os
import runpy
import sys
import traceback

SCRIPT = sys.argv[1]
FIG_DIR = os.path.dirname(os.path.abspath(SCRIPT))
_count = [0]


def _next_path():
    _count[0] += 1
    return os.path.join(FIG_DIR, "figure_%02d.png" % _count[0])


def _input(prompt=""):
    sys.stdout.write(str(prompt))
    sys.stdout.flush()
    line = sys.stdin.readline()
    if not line:
        raise EOFError("EOF when reading a line")
    line = line.rstrip("\n")
    sys.stdout.write(line + "\n")
    return line


builtins.input = _input
os.environ.setdefault("MPLBACKEND", "Agg")

if os.environ.get("LF_NO_NET") == "1":
    # Only connections to this machine; lab programs don't need the internet.
    import socket

    def _local(addr):
        if not isinstance(addr, tuple) or not addr:
            return True  # unix socket
        host = str(addr[0]).lower().strip("[]")
        return host in ("localhost", "::1") or host.startswith(("127.", "::ffff:127."))

    def _guard(original):
        def connect(self, addr):
            if not _local(addr):
                raise OSError(101, "Network is unreachable (lab programs can't reach the internet here)")
            return original(self, addr)
        return connect

    socket.socket.connect = _guard(socket.socket.connect)
    socket.socket.connect_ex = _guard(socket.socket.connect_ex)

if os.environ.get("LF_MPL") == "1":
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        def _show(*_a, **_k):
            for num in plt.get_fignums():
                plt.figure(num).savefig(_next_path(), dpi=110, bbox_inches="tight")
            plt.close("all")

        plt.show = _show
        import atexit

        atexit.register(_show)
    except Exception:  # matplotlib missing or broken: the script will report it
        pass

if os.environ.get("LF_CV2") == "1":
    try:
        import cv2

        cv2.imshow = lambda _name, img: cv2.imwrite(_next_path(), img)
        cv2.waitKey = lambda *_a, **_k: -1
        cv2.destroyAllWindows = lambda *_a, **_k: None
        cv2.destroyWindow = lambda *_a, **_k: None
    except Exception:
        pass

if os.environ.get("LF_PIL") == "1":
    try:
        from PIL import Image

        Image.Image.show = lambda self, *_a, **_k: self.save(_next_path())
    except Exception:
        pass

sys.argv = [SCRIPT]
sys.path.insert(0, FIG_DIR)
try:
    runpy.run_path(SCRIPT, run_name="__main__")
except SystemExit:
    raise
except BaseException as exc:  # print like the interpreter would, minus our frames
    sys.stdout.flush()
    tb = exc.__traceback__
    while tb is not None and os.path.abspath(tb.tb_frame.f_code.co_filename) != os.path.abspath(SCRIPT):
        tb = tb.tb_next
    traceback.print_exception(type(exc), exc, tb)
    sys.exit(1)
