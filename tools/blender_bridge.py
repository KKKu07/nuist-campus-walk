"""Tiny client for the official Blender Lab "MCP" extension (Blender 5.1+).

The extension (``%APPDATA%/Blender Foundation/Blender/5.1/extensions/user_default/mcp``)
runs a TCP server inside Blender (default ``localhost:9876``). Protocol:

    request : JSON + b"\\0"   {"type": "execute", "code": "<python>", "strict_json": true}
    response: JSON + b"\\0"   {"status": "ok"|"error", "result": {...}, "message": "...",
                               "stdout": "...", "stderr": "..."}

The code runs on Blender's main thread with ``bpy`` importable; whatever it
stores in the dict ``result`` comes back. ``sys.exit`` and a few ops are blocked.
NOTE: requests in the ``{"type": "get_scene_info"}`` style (ahujasid/blender-mcp)
are NOT understood by this extension, and a request without the trailing NUL
byte is never executed (the server just waits, then answers "Client timed out").

Usage:
    python tools/blender_bridge.py info
    python tools/blender_bridge.py exec -c "import bpy; result['n'] = len(bpy.data.objects)"
    python tools/blender_bridge.py run some_script.py [--arg key=value ...]

Only stdlib; works with the project .venv or any Python 3.9+.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path

HOST = "127.0.0.1"
PORT = 9876


class BlenderError(RuntimeError):
    pass


def call(code: str, host: str = HOST, port: int = PORT, timeout: float = 600.0,
         strict_json: bool = False) -> dict:
    """Execute ``code`` inside the running Blender and return the raw response dict."""
    payload = json.dumps({"type": "execute", "code": code, "strict_json": strict_json}).encode("utf-8") + b"\0"
    with socket.create_connection((host, port), timeout=10) as s:
        s.sendall(payload)
        s.settimeout(timeout)
        buf = bytearray()
        while b"\0" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf.extend(chunk)
    if not buf:
        raise BlenderError("connection closed without a response")
    return json.loads(bytes(buf).split(b"\0", 1)[0].decode("utf-8"))


def execute(code: str, **kw) -> dict:
    """Like ``call`` but raises on error and returns only ``result``; echoes stdout/stderr."""
    resp = call(code, **kw)
    if resp.get("stdout"):
        sys.stdout.write(resp["stdout"])
    if resp.get("stderr"):
        sys.stderr.write(resp["stderr"])
    if resp.get("status") != "ok":
        raise BlenderError(resp.get("message", repr(resp)))
    return resp.get("result", {})


def run_file(path: str | Path, args: dict | None = None, **kw) -> dict:
    """Run a local .py file inside Blender. ``ARGS`` (dict) is visible to the script."""
    p = Path(path).resolve()
    code = (
        "ARGS = {args!r}\n"
        "__file__ = {path!r}\n"
        "exec(compile(open(__file__, encoding='utf-8').read(), __file__, 'exec'))\n"
    ).format(args=args or {}, path=str(p))
    return execute(code, **kw)


SCENE_INFO = r"""
import bpy
sc = bpy.context.scene
result.update({
    "blender": bpy.app.version_string,
    "file": bpy.data.filepath,
    "scene": sc.name,
    "frame": sc.frame_current,
    "render_engine": sc.render.engine,
    "unit_system": sc.unit_settings.system,
    "objects": [
        {"name": o.name, "type": o.type, "loc": [round(v, 3) for v in o.location],
         "dims": [round(v, 3) for v in o.dimensions]}
        for o in sc.objects
    ][:200],
    "n_objects": len(sc.objects),
    "materials": len(bpy.data.materials),
})
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--timeout", type=float, default=600.0)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("info", help="print scene info")
    e = sub.add_parser("exec", help="execute python code")
    e.add_argument("-c", "--code", required=True)
    r = sub.add_parser("run", help="execute a local python file")
    r.add_argument("file")
    r.add_argument("--arg", action="append", default=[], help="key=value, available as ARGS[key]")
    a = ap.parse_args(argv)
    kw = {"host": a.host, "port": a.port, "timeout": a.timeout}
    try:
        if a.cmd == "info":
            res = execute(SCENE_INFO, **kw)
        elif a.cmd == "exec":
            res = execute(a.code, **kw)
        else:
            args = dict(kv.split("=", 1) for kv in a.arg)
            res = run_file(a.file, args, **kw)
    except (OSError, BlenderError) as ex:
        print("ERROR:", ex, file=sys.stderr)
        return 1
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
