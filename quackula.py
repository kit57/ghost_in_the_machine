#!/usr/bin/env python3
"""
Quackula - the haunted rubber duck that exorcises your codebase.

Quackula was a rubber duck on a programmer's desk from 1994 until it fell
behind a radiator in 2009. Now it haunts codebases. It sniffs out cursed code
(swallowed exceptions, eldritch functions, ancient TODOs...), performs a
ritual, and channels a local open-weight model through Ollama to explain each
curse and how to lift it. Your code never leaves your machine.

Usage:
    python quackula.py exorcise [PATH] [--max N] [--report FILE]
    python quackula.py debug [--file FILE]

Options for both: --model NAME (default gemma3:4b), --fast, --offline
Stdlib only. Needs Ollama running locally (falls back to canned wisdom if not).
"""
import argparse
import ast
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
if not OLLAMA.startswith("http"):
    OLLAMA = "http://" + OLLAMA
DEFAULT_MODEL = os.environ.get("QUACKULA_MODEL", "gemma3:4b")

CODE_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".cs", ".go", ".rb",
             ".php", ".c", ".cpp", ".h", ".hpp", ".rs", ".kt", ".swift"}
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist",
             "build", "target", ".idea", ".vscode", "vendor"}

TYPE_DELAY = 0.012
DRAMA = 1.0  # multiplier for dramatic pauses; 0 with --fast
TTY = True
CPU_ONLY = False  # set by --cpu, or automatically when the GPU backend crashes


# --------------------------------------------------------------------------
# Terminal effects
# --------------------------------------------------------------------------

class C:
    R = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GRN = "\033[32m"
    YEL = "\033[33m"
    MAG = "\033[35m"
    CYN = "\033[36m"
    WHT = "\033[37m"


def setup_terminal():
    global TTY
    TTY = sys.stdout.isatty()
    if os.name == "nt":
        os.system("")  # enables ANSI escape codes on Windows 10+ consoles
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    if os.environ.get("NO_COLOR") or not TTY:
        for name in vars(C):
            if not name.startswith("_"):
                setattr(C, name, "")


def pause(seconds):
    if DRAMA:
        time.sleep(seconds * DRAMA)


def type_out(text, color="", delay=None):
    delay = TYPE_DELAY if delay is None else delay
    sys.stdout.write(color)
    for ch in text:
        sys.stdout.write(ch)
        sys.stdout.flush()
        if delay:
            time.sleep(delay)
    sys.stdout.write(C.R)
    sys.stdout.flush()


def zalgo(text, intensity=2):
    marks = [chr(c) for c in range(0x0300, 0x036F)]
    return "".join(ch + "".join(random.choice(marks) for _ in range(intensity))
                   if ch.isalpha() else ch for ch in text)


def flicker(text, times=5):
    if not TTY or not DRAMA:
        print(f"{C.BOLD}{C.RED}{text}{C.R}")
        return
    for i in range(times):
        color = (C.RED, C.MAG, C.WHT)[i % 3]
        shown = zalgo(text, 1) if i % 2 else text
        sys.stdout.write(f"\r\033[K{C.BOLD}{color}{shown}{C.R}")
        sys.stdout.flush()
        pause(0.12)
    sys.stdout.write(f"\r\033[K{C.BOLD}{C.RED}{text}{C.R}\n")


DUCK = [
    r"          __          ",
    r"      ___( x)>   ~    ",
    r"      \ <_. )   ~ ~   ",
    r"  ~~~~ `---'  ~       ",
]


def rise():
    """The duck rises from the bathwater of the beyond."""
    print()
    for line in DUCK:
        type_out(line + "\n", C.CYN, delay=TYPE_DELAY / 3)
        pause(0.15)
    pause(0.3)
    print(f"  {C.BOLD}{C.MAG}{zalgo('QUACKULA', 1)}{C.R}  "
          f"{C.DIM}the haunted rubber duck{C.R}\n")
    pause(0.4)


# --------------------------------------------------------------------------
# Curse detection
# --------------------------------------------------------------------------

CURSES = {
    "swallowed-exception": {
        "title": "The Silent Scream",
        "chant": "Exceptio silentium... SPEAK!",
        "fallback": "An error is caught and then... nothing. Its screams echo "
                    "forever where no log can hear them. Log it, handle it, or "
                    "let it rise. Catch only the exceptions you can actually fix.",
    },
    "eldritch-function": {
        "title": "The Eldritch Function",
        "chant": "Spaghettus codicus... BEGONE!",
        "fallback": "This function has grown tentacles. Every scroll reveals new "
                    "horrors. Split it into small, named steps, one job each, "
                    "and the beast will shrink back into the deep.",
    },
    "abyssal-nesting": {
        "title": "The Abyss of Indentation",
        "chant": "Ex profundis indentationis... ASCENDE!",
        "fallback": "I stared into this nesting and it stared back. Use guard "
                    "clauses and early returns to climb out of the pit, one "
                    "level at a time.",
    },
    "ancient-todo": {
        "title": "The Unkept Promise",
        "chant": "Promissum oblitum... FULFILL OR BE FORGOTTEN!",
        "fallback": "A promise left in a comment becomes a ghost. Do the thing, "
                    "turn it into a real ticket, or delete it and let it rest.",
    },
    "whispering-debug": {
        "title": "The Whispering Logs",
        "chant": "Console logus... SILENTIUM!",
        "fallback": "Debug whispers left behind haunt every user's console. Remove "
                    "them, or use a real logger with levels you can turn down.",
    },
    "commented-corpse": {
        "title": "The Commented Corpse",
        "chant": "Codex mortuus... REQUIESCAT IN GIT!",
        "fallback": "Dead code, buried in comments, neither alive nor gone. Git "
                    "remembers everything. Delete it and let version control "
                    "be its tomb.",
    },
    "haunted-file": {
        "title": "The Haunted Manor",
        "chant": "Domus maledicta... DIVIDE ET IMPERA!",
        "fallback": "This file has too many rooms, and something lives in each one. "
                    "Split it into modules with clear responsibilities.",
    },
    "unparseable": {
        "title": "The Unspeakable Tongue",
        "chant": "Syntaxis corrupta... REVEAL THYSELF!",
        "fallback": "Even the interpreter cannot read this. Fix the syntax error "
                    "before the possession spreads.",
    },
}

GENERIC_CHANTS = [
    "In nomine Linus, et Guido, et Spiritus Stack Overflow...",
    "By the power of git blame, I compel thee!",
    "Quack quack... VADE RETRO!",
    "Refactorum maximus!",
    "Legacius codex, return to the void!",
]

AFTERLIFE_ASIDES = [
    "*The duck stares into the void. The void squeaks back.*",
    "*Somewhere, a radiator clanks. The duck shudders.*",
    "*A faint smell of bathwater and ozone fills the room.*",
    "*The candle flickers. The duck pretends that was intentional.*",
    "*\"No bathtubs in the beyond,\" the duck mutters. \"Not one.\"*",
]


@dataclass
class Curse:
    path: Path
    line: int
    kind: str
    severity: int
    snippet: str   # short excerpt shown in the terminal
    context: str   # longer excerpt sent to the model
    note: str = ""
    focus: str = ""  # the exact cursed line(s)


def excerpt(lines, start, end=None, ctx=2, max_lines=14, gutter=True):
    end = end or start
    lo = max(1, start - ctx)
    hi = min(len(lines), end + ctx, lo + max_lines - 1)
    if not gutter:  # small models copy line numbers into their fixes
        return "\n".join(lines[lo - 1:hi])
    return "\n".join(f"{i:>4} | {lines[i - 1]}" for i in range(lo, hi + 1))


TODO_RE = re.compile(r"(#|//|/\*|^\s*\*).*\b(TODO|FIXME|HACK|XXX)\b")
DEBUG_RE = re.compile(r"\bconsole\.(log|debug)\(|^\s*debugger;|System\.out\.println\(|"
                      r"\bvar_dump\(|\bbreakpoint\(\)|pdb\.set_trace\(\)")
EMPTY_CATCH_RE = re.compile(r"catch\s*(\([^)]*\))?\s*\{\s*\}")
COMMENT_RE = re.compile(r"^\s*(#|//)\s?(.*)$")
CODEISH_RE = re.compile(r"[;=(){}\[\]]|\breturn\b|\bdef\b|\bfunction\b|\bif\b")
FUNC_START_RE = re.compile(r"\bfunction\b[^(]*\(|=>\s*\{|"
                           r"^\s*(public|private|protected|static|func|fn)\b.*\(")

LONG_FUNC = 40
HUGE_FILE = 400
DEEP_NEST = 6


def curse(kind, severity, path, lines, start, end=None, note=""):
    return Curse(path, start, kind, severity,
                 excerpt(lines, start, end),
                 excerpt(lines, start, end, ctx=3, max_lines=70, gutter=False), note,
                 excerpt(lines, start, end, ctx=0, max_lines=8, gutter=False).strip())


def scan_python(path, text, lines):
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        yield curse("unparseable", 3, path, lines, e.lineno or 1, note=str(e.msg))
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            silent = all(isinstance(s, ast.Pass) or
                         (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)
                          and s.value.value is Ellipsis) for s in node.body)
            if silent:
                sev = 3 if node.type is None else 2
                yield curse("swallowed-exception", sev, path, lines, node.lineno,
                            node.end_lineno, "bare except" if node.type is None else "")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            length = node.end_lineno - node.lineno + 1
            if length > LONG_FUNC:
                yield curse("eldritch-function", 3 if length > 2 * LONG_FUNC else 2,
                            path, lines, node.lineno, note=f"{node.name}: {length} lines")


def scan_braces(path, text, lines):
    for m in EMPTY_CATCH_RE.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        yield curse("swallowed-exception", 3, path, lines, line)
    i = 0
    while i < len(lines):
        if not FUNC_START_RE.search(lines[i]):
            i += 1
            continue
        depth, started, end = 0, False, None
        for j in range(i, len(lines)):
            for ch in lines[j]:
                if ch == "{":
                    depth, started = depth + 1, True
                elif ch == "}":
                    depth -= 1
            if started and depth <= 0:
                end = j
                break
            if not started and j > i + 2:
                break
        if end is None:
            i += 1
            continue
        length = end - i + 1
        if length > LONG_FUNC:
            yield curse("eldritch-function", 3 if length > 2 * LONG_FUNC else 2,
                        path, lines, i + 1, note=f"{length} lines")
        i = end + 1


def scan_lines(path, lines):
    debug_hits, deepest, corpse_start, corpse_len = [], (0, 0), None, 0
    indents = [len(l) - len(l.lstrip(" ")) for l in lines if l.strip() and l.startswith(" ")]
    unit = min((n for n in indents if n), default=4)
    unit = unit if unit in (2, 4) else 4

    for n, raw in enumerate(lines, 1):
        line = raw.expandtabs(unit)
        if TODO_RE.search(line):
            sev = 2 if re.search(r"\b(HACK|XXX|FIXME)\b", line) else 1
            yield curse("ancient-todo", sev, path, lines, n, note=line.strip())
        if DEBUG_RE.search(line):
            debug_hits.append(n)
        if line.strip() and not COMMENT_RE.match(line):
            depth = (len(line) - len(line.lstrip(" "))) // unit
            if depth > deepest[0]:
                deepest = (depth, n)
        cm = COMMENT_RE.match(line)
        if cm and CODEISH_RE.search(cm.group(2)) and not TODO_RE.search(line):
            corpse_start = corpse_start or n
            corpse_len += 1
        else:
            if corpse_len >= 3:
                yield curse("commented-corpse", 1, path, lines, corpse_start,
                            corpse_start + corpse_len - 1, f"{corpse_len} buried lines")
            corpse_start, corpse_len = None, 0
    if corpse_len >= 3:
        yield curse("commented-corpse", 1, path, lines, corpse_start,
                    corpse_start + corpse_len - 1, f"{corpse_len} buried lines")

    if debug_hits:
        yield curse("whispering-debug", 2 if len(debug_hits) > 3 else 1, path, lines,
                    debug_hits[0], note=f"{len(debug_hits)} whispers in this file")
    if deepest[0] >= DEEP_NEST:
        yield curse("abyssal-nesting", 3 if deepest[0] >= DEEP_NEST + 2 else 2,
                    path, lines, deepest[1], note=f"{deepest[0]} levels deep")
    if len(lines) > HUGE_FILE:
        yield curse("haunted-file", 2, path, lines, 1, note=f"{len(lines)} lines")


def code_files(root):
    if root.is_file():
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in CODE_EXTS:
                yield p


def scan(root):
    found, files = [], 0
    for path in code_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        files += 1
        lines = text.splitlines()
        found.extend(scan_lines(path, lines))
        if path.suffix == ".py":
            found.extend(scan_python(path, text, lines))
        else:
            found.extend(scan_braces(path, text, lines))
    return found, files


def pick(curses, n):
    """Worst curses first, but show off a variety of hauntings."""
    ranked = sorted(curses, key=lambda c: -c.severity)
    chosen, seen = [], set()
    for c in ranked:
        if c.kind not in seen:
            chosen.append(c)
            seen.add(c.kind)
    chosen += [c for c in ranked if c not in chosen]
    return sorted(chosen[:n], key=lambda c: -c.severity)


# --------------------------------------------------------------------------
# Channeling the spirit (local model via Ollama)
# --------------------------------------------------------------------------

PERSONA = (
    "You are Quackula, the ghost of a rubber duck that sat on a programmer's desk "
    "from 1994 until it fell behind a radiator in 2009. You now haunt codebases. "
    "You are dramatic, gothic, a little petty, fond of duck puns, and genuinely "
    "excellent at code review. You sometimes get briefly distracted complaining "
    "about the afterlife (ectoplasm, noisy poltergeists, no bathtubs in the beyond) "
    "before snapping back to the task. Write plain text: no markdown headings, no "
    "bold. Code may go in ``` fences."
)

EXORCISE_TASK = (
    "A cursed piece of code has been found in {file} near line {line}.\n"
    "Curse: {title} ({kind}){note}\n"
    "The cursed line(s):\n```\n{focus}\n```\n"
    "Known cure for this curse: {cure}\n\n"
    "Surrounding code for context:\n```\n{context}\n```\n\n"
    "Lift ONLY this curse by applying the known cure to the cursed line(s). Do "
    "not change behavior or suggest unrelated changes. Write three short "
    "paragraphs without numbering: first, in one or two dramatic sentences, the "
    "evil this curse causes. Second, the fix: explain it briefly and show a small "
    "corrected snippet (no line numbers) only if the cure involves changing code. "
    "Third, one short ominous closing line. Stay under 130 words."
)

DEBUG_TASK = (
    " A programmer has come to you to talk through a bug: classic rubber duck "
    "debugging. Help them find the bug themselves. Ask one sharp clarifying "
    "question at a time, restate what they said to expose hidden assumptions, and "
    "suggest concrete things to check (print a value, read the full error, test "
    "the input). In about one reply out of three, get distracted by an afterlife "
    "complaint, then snap back. Stay under 120 words."
)


def summon(model):
    """Check that Ollama is awake and has the model. Returns None if all good."""
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=3) as r:
            names = [m["name"] for m in json.load(r).get("models", [])]
    except (urllib.error.URLError, OSError, ValueError):
        return f"No spirit answers at {OLLAMA}. Is Ollama running? (ollama serve)"
    if not any(n == model or n.split(":")[0] == model for n in names):
        return f"Model '{model}' not found. Try: ollama pull {model}"
    return None


def channel(messages, model):
    """Stream a reply from the local model, typewriter style. Returns the text."""
    global CPU_ONLY
    options = {"temperature": 0.6}
    if CPU_ONLY:
        options["num_gpu"] = 0
    body = json.dumps({"model": model, "messages": messages, "stream": True,
                       "options": options}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    waiting = "  🕯  the duck is channeling..."
    if TTY:
        sys.stdout.write(f"{C.DIM}{waiting}{C.R}")
        sys.stdout.flush()
    try:
        resp = urllib.request.urlopen(req, timeout=300)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        if CPU_ONLY or not re.search(r"CUDA|llama-server|GPU", detail):
            raise RuntimeError(detail or str(e)) from e
        # Old GPU drivers crash Ollama's CUDA backend; the CPU still works.
        CPU_ONLY = True
        if TTY:
            sys.stdout.write("\r\033[K")
        print(f"  {C.YEL}⚠ The GPU spirits refuse to cooperate. "
              f"Channeling through the CPU instead (slower).{C.R}")
        return channel(messages, model)
    out, first = [], True
    with resp as r:
        for raw in r:
            if not raw.strip():
                continue
            msg = json.loads(raw)
            if "error" in msg:
                raise RuntimeError(msg["error"])
            tok = msg.get("message", {}).get("content", "")
            if tok:
                if first:
                    sys.stdout.write("\r\033[K  " if TTY else "  ")
                    first = False
                    tok = tok.lstrip()
                out.append(tok)
                type_out(tok.replace("**", "").replace("\n", "\n  "), C.CYN)
            if msg.get("done"):
                break
    print()
    return "".join(out).strip()


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------

def exorcise(args):
    root = Path(args.path).resolve()
    if not root.exists():
        sys.exit(f"Quackula cannot find {root}. Even ghosts need a path.")

    rise()
    type_out("  Quackula awakens. Something in this code has disturbed its rest...\n",
             C.YEL)
    pause(0.5)
    type_out(f"  Sniffing {root.name or root} for curses", C.DIM)
    for _ in range(3):
        pause(0.3)
        type_out(".", C.DIM)
    print("\n")

    found, files = scan(root)
    if not found:
        type_out("  ...nothing. This code is pure. Suspiciously pure.\n", C.GRN)
        type_out("  The duck will be watching.\n\n", C.DIM)
        return

    score = sum(c.severity for c in found)
    level = min(100, score * 4)
    bar = "█" * (level // 5) + "░" * (20 - level // 5)
    print(f"  {C.BOLD}Files sniffed:{C.R}    {files}")
    print(f"  {C.BOLD}Curses detected:{C.R}  {len(found)}")
    print(f"  {C.BOLD}Possession level:{C.R} {C.RED}{bar}{C.R} {level}%\n")
    counts = {}
    for c in found:
        counts[c.kind] = counts.get(c.kind, 0) + 1
    for kind, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"    {C.MAG}☠{C.R} {CURSES[kind]['title']:<28} {C.DIM}x{n}{C.R}")
    print()
    pause(0.8)

    problem = "Offline mode." if args.offline else summon(args.model)
    if problem:
        print(f"  {C.YEL}⚠ {problem}{C.R}")
        print(f"  {C.DIM}The duck will rely on its own ancient memory instead.{C.R}\n")

    report = []
    targets = pick(found, args.max)
    for i, c in enumerate(targets, 1):
        info = CURSES[c.kind]
        rel = c.path.relative_to(root) if root.is_dir() else c.path.name
        print(f"{C.DIM}{'─' * 64}{C.R}")
        print(f"  {C.BOLD}Curse {i}/{len(targets)}: {C.RED}{info['title']}{C.R}  "
              f"{C.DIM}{rel}:{c.line}{(' — ' + c.note) if c.note else ''}{C.R}\n")
        print(f"{C.DIM}{c.snippet}{C.R}\n")
        pause(0.6)
        flicker(f"  🕯  {random.choice([info['chant']] * 2 + GENERIC_CHANTS)}")
        print()
        pause(0.4)

        text = None
        if not problem:
            prompt = EXORCISE_TASK.format(
                title=info["title"], kind=c.kind, note=f" — {c.note}" if c.note else "",
                cure=info["fallback"], file=rel, line=c.line, context=c.context,
                focus=c.focus)
            try:
                text = channel([{"role": "system", "content": PERSONA},
                                {"role": "user", "content": prompt}], args.model)
            except (urllib.error.URLError, OSError, RuntimeError) as e:
                print(f"\n  {C.YEL}⚠ The connection to the beyond broke: {e}{C.R}")
        if text is None:
            text = info["fallback"]
            sys.stdout.write("  ")
            type_out(text + "\n", C.CYN)
        report.append((c, rel, info["title"], text))

        if random.random() < 0.35:
            print(f"\n  {C.DIM}{random.choice(AFTERLIFE_ASIDES)}{C.R}")
        print()
        pause(0.6)

    print(f"{C.DIM}{'─' * 64}{C.R}")
    flicker("  ✨ THE RITUAL IS COMPLETE ✨", times=4)
    remaining = len(found) - len(targets)
    if remaining:
        type_out(f"  {remaining} lesser curses still lurk. Run me again with "
                 f"--max {len(found)} if you dare.\n", C.DIM)
    type_out("  The code is cleansed... for now. Quackula sinks back beneath the "
             "bathwater.\n\n", C.YEL)

    if args.report:
        write_report(Path(args.report), root, files, found, level, report)
        print(f"  {C.GRN}📜 Exorcism report written to {args.report}{C.R}\n")


def write_report(out, root, files, found, level, report):
    parts = [f"# Exorcism Report: `{root.name}`\n",
             f"Performed by **Quackula**, the haunted rubber duck "
             f"({time.strftime('%Y-%m-%d %H:%M')}).\n",
             f"- Files sniffed: {files}\n- Curses detected: {len(found)}\n"
             f"- Possession level: {level}%\n"]
    for c, rel, title, text in report:
        parts.append(f"\n## {title}: `{rel}:{c.line}`\n")
        if c.note:
            parts.append(f"_{c.note}_\n")
        parts.append(f"\n```\n{c.snippet}\n```\n\n{text}\n")
    out.write_text("".join(parts), encoding="utf-8")


def debug(args):
    rise()
    if args.offline:
        sys.exit("  The duck cannot listen offline. It needs a local model.")
    problem = summon(args.model)
    if problem:
        sys.exit(f"  {problem}\n  Quackula needs a local model to listen to you.")
    type_out("  Ah. A mortal with a bug. Sit. Speak. The duck is listening.\n", C.YEL)
    print(f"  {C.DIM}(type 'exit' to banish the duck){C.R}\n")

    messages = [{"role": "system", "content": PERSONA + DEBUG_TASK}]
    if args.file:
        code = Path(args.file).read_text(encoding="utf-8", errors="replace")
        messages.append({"role": "user", "content":
                         f"Here is the code I'm working on ({args.file}):\n```\n"
                         f"{code[:12000]}\n```\nDon't solve it yet, just acknowledge it."})
        messages.append({"role": "assistant", "content":
                         "I have gazed upon your code. Now tell me what haunts it."})
        print(f"  {C.DIM}(the duck has read {args.file}){C.R}\n")

    while True:
        try:
            said = input(f"{C.GRN}  you > {C.R}").strip()
        except (EOFError, KeyboardInterrupt):
            said = "exit"
        if said.lower() in {"exit", "quit", "bye"}:
            type_out("\n  The duck sinks back into the bathwater. "
                     "It will return when you least expect it.\n\n", C.YEL)
            return
        if not said:
            continue
        messages.append({"role": "user", "content": said})
        print()
        try:
            reply = channel(messages, args.model)
        except (urllib.error.URLError, OSError, RuntimeError) as e:
            print(f"\n  {C.YEL}⚠ The connection to the beyond broke: {e}{C.R}\n")
            messages.pop()
            continue
        messages.append({"role": "assistant", "content": reply})
        print()


def main():
    global TYPE_DELAY, DRAMA, CPU_ONLY
    setup_terminal()
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Ollama model to channel (default {DEFAULT_MODEL})")
    common.add_argument("--fast", action="store_true", help="skip the theatrics")
    common.add_argument("--offline", action="store_true",
                        help="don't call the model; use the duck's canned wisdom")
    common.add_argument("--cpu", action="store_true",
                        help="run the model on CPU only (for old GPU drivers)")

    parser = argparse.ArgumentParser(
        prog="quackula", description="The haunted rubber duck that exorcises your code.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("exorcise", parents=[common], help="scan code and lift its curses")
    ex.add_argument("path", nargs="?", default=".")
    ex.add_argument("--max", type=int, default=5, help="curses to exorcise (default 5)")
    ex.add_argument("--report", help="write a markdown exorcism report to this file")
    db = sub.add_parser("debug", parents=[common], help="talk your bug through with the duck")
    db.add_argument("--file", help="let the duck read this file first")

    args = parser.parse_args()
    if args.fast:
        TYPE_DELAY, DRAMA = 0, 0
    CPU_ONLY = args.cpu
    (exorcise if args.cmd == "exorcise" else debug)(args)


if __name__ == "__main__":
    main()
