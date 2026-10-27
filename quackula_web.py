"""
Quackula's séance room - a local web UI for the haunted rubber duck.

Started with `python quackula.py ui`. Serves quackula_ui.html on 127.0.0.1 and
exposes the same scanning, exorcising and debugging the CLI does. Like the CLI,
nothing leaves your machine: the only outbound call is to your local Ollama.
Stdlib only.
"""
import json
import urllib.error
import urllib.request
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import quackula as q

PAGE = Path(__file__).with_name("quackula_ui.html")
LOCAL_HOSTS = {"127.0.0.1", "localhost"}


def models():
    try:
        with urllib.request.urlopen(f"{q.OLLAMA}/api/tags", timeout=3) as r:
            return sorted(m["name"] for m in json.load(r).get("models", []))
    except (urllib.error.URLError, OSError, ValueError):
        return []


def rel_path(path, root):
    return (path.relative_to(root) if root.is_dir() else Path(path.name)).as_posix()


def curse_json(i, c, root):
    d = asdict(c)
    info = q.CURSES[c.kind]
    d.update(id=i, path=str(c.path), rel=rel_path(c.path, root),
             title=info["title"], chant=info["chant"])
    return d


def curse_from(d):
    return q.Curse(Path(d["path"]), int(d["line"]), d["kind"], int(d["severity"]),
                   d["snippet"], d["context"], d.get("note", ""), d.get("focus", ""))


class Handler(BaseHTTPRequestHandler):
    server_version = "Quackula/1994"
    gone = False  # the browser hung up mid-stream

    def log_message(self, *args):
        pass  # the duck does not narrate every request

    # -- plumbing ----------------------------------------------------------

    def local(self):
        # Refuse anything not addressed to localhost, so a malicious web page
        # can't reach the duck through DNS rebinding.
        host = self.headers.get("Host", "").rsplit(":", 1)[0].strip("[]")
        return host in LOCAL_HOSTS

    def send(self, status, body, ctype="application/json"):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def start_stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def emit(self, **msg):
        """Send one line of a stream. Returns False once the browser is gone."""
        if not self.gone:
            try:
                self.wfile.write(json.dumps(msg).encode() + b"\n")
                self.wfile.flush()
            except OSError:
                self.gone = True
        return not self.gone

    def stream_reply(self, messages, model):
        """Relay model tokens to the browser. Returns the text, or None on failure."""
        out = []
        try:
            tokens = q.open_channel(messages, model, warn=lambda t: self.emit(warn=t))
            try:
                for tok in tokens:
                    out.append(tok)
                    if not self.emit(t=tok):
                        break
            finally:
                tokens.close()
        except (urllib.error.URLError, OSError, RuntimeError) as e:
            self.emit(warn=f"The connection to the beyond broke: {e}")
            return None
        return "".join(out)

    # -- routes ------------------------------------------------------------

    def do_GET(self):
        if not self.local():
            return self.send(403, {"error": "The duck only haunts localhost."})
        url = urlparse(self.path)
        if url.path == "/":
            return self.send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        if url.path == "/api/status":
            model = parse_qs(url.query).get("model", [self.server.defaults["model"]])[0]
            return self.send(200, {"problem": q.summon(model), "models": models(),
                                   "cpu": q.CPU_ONLY, **self.server.defaults})
        self.send(404, {"error": "Nothing haunts this path."})

    def do_POST(self):
        if not self.local() or "json" not in self.headers.get("Content-Type", ""):
            return self.send(403, {"error": "The duck only haunts localhost."})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        except ValueError:
            return self.send(400, {"error": "The duck cannot read this scroll."})
        route = {"/api/scan": self.scan, "/api/cure": self.cure,
                 "/api/chat": self.chat, "/api/report": self.report}.get(self.path)
        if not route:
            return self.send(404, {"error": "Nothing haunts this path."})
        if body.get("cpu"):
            q.CPU_ONLY = True
        route(body)

    def scan(self, body):
        root = Path(body.get("path") or ".").expanduser().resolve()
        if not root.exists():
            return self.send(400, {"error": f"Quackula cannot find {root}. "
                                            "Even ghosts need a path."})
        found, files = q.scan(root)
        counts = {}
        for c in found:
            counts[c.kind] = counts.get(c.kind, 0) + 1
        self.send(200, {
            "root": str(root), "name": root.name or str(root), "files": files,
            "level": q.possession(found),
            "counts": [{"kind": k, "title": q.CURSES[k]["title"], "n": n}
                       for k, n in sorted(counts.items(), key=lambda kv: -kv[1])],
            "curses": [curse_json(i, c, root)
                       for i, c in enumerate(q.pick(found, len(found)))],
        })

    def cure(self, body):
        d = body["curse"]
        c = curse_from(d)
        fallback = q.CURSES[c.kind]["fallback"]
        self.start_stream()
        problem = "Offline mode." if body.get("offline") else q.summon(body["model"])
        if problem:
            self.emit(warn=problem, offline=True)
            self.emit(t=fallback)
            return
        messages = [{"role": "system", "content": q.PERSONA},
                    {"role": "user", "content": q.exorcise_prompt(c, d["rel"])}]
        if self.stream_reply(messages, body["model"]) is None:
            self.emit(t=fallback)

    def chat(self, body):
        file = (body.get("file") or "").strip()
        try:
            messages = q.debug_messages(file or None)
        except OSError as e:
            return self.send(400, {"error": f"The duck cannot read {file}: {e.strerror}"})
        messages += [{"role": m["role"], "content": str(m["content"])}
                     for m in body.get("messages", [])
                     if m.get("role") in ("user", "assistant")]
        if body.get("offline"):
            return self.send(400, {"error": "The duck cannot listen offline. "
                                            "It needs a local model."})
        problem = q.summon(body["model"])
        if problem:
            return self.send(400, {"error": problem})
        self.start_stream()
        self.stream_reply(messages, body["model"])

    def report(self, body):
        entries = []
        for e in body.get("entries", []):
            c = curse_from(e["curse"])
            entries.append((c, e["curse"]["rel"], q.CURSES[c.kind]["title"], e["text"]))
        md = q.report_markdown(body["name"], body["files"], body["total"],
                               body["level"], entries)
        self.send(200, md.encode(), "text/markdown; charset=utf-8")


def serve(args):
    q.setup_terminal()
    q.CPU_ONLY = args.cpu
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.daemon_threads = True
    server.defaults = {"model": args.model, "path": str(Path(args.path).resolve()),
                       "offline": args.offline, "fast": args.fast}
    url = f"http://127.0.0.1:{args.port}/"
    print(f"\n  {q.C.BOLD}{q.C.MAG}QUACKULA{q.C.R}  {q.C.DIM}the séance room is open{q.C.R}")
    print(f"  {q.C.CYN}{url}{q.C.R}")
    print(f"  {q.C.DIM}(only reachable from this machine; Ctrl+C to banish the duck){q.C.R}\n")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"  {q.C.YEL}The duck sinks back into the bathwater.{q.C.R}\n")
    finally:
        server.server_close()
