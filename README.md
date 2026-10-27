# Quackula — the haunted rubber duck

Quackula was a rubber duck on a programmer's desk from 1994 until it fell behind
a radiator in 2009. Now it haunts codebases.

- **`exorcise`**: sniffs your code for curses (swallowed exceptions, eldritch
  functions, abyssal nesting, ancient TODOs, debug whispers, commented-out
  corpses), performs a ritual, and explains how to lift each curse.
- **`debug`**: classic rubber-duck debugging, except the duck talks back, asks
  sharp questions, and keeps complaining that there are no bathtubs in the beyond.

Everything runs locally on an open-weight model through [Ollama](https://ollama.com).
Your code never leaves your machine.

## Run it

```bash
ollama pull gemma3:4b
python quackula.py exorcise haunted_sample          # full theatrics
python quackula.py exorcise path/to/repo --max 8 --report exorcism.md
python quackula.py debug --file my_buggy_script.py
python quackula.py ui                               # the séance room, in your browser
```

### The séance room (web UI)

Prefer clicking to typing? `python quackula.py ui [PATH]` opens a local web page
that does everything the CLI does: sniff a folder for curses, exorcise them one
at a time or all at once, download the exorcism report, and hold a debugging
séance in a chat window. Every screen also shows the equivalent CLI command, so you
can switch between the two whenever you like.

The page is served only on `127.0.0.1` (default port 8666, change with `--port`;
`--no-browser` skips opening a tab) and talks only to your local Ollama, so
your code still never leaves your machine. It accepts the same `--model`,
`--fast`, `--offline` and `--cpu` flags as starting defaults.

Python 3.8+, standard library only. Options:

| Flag | What it does |
|---|---|
| `--model NAME` | any Ollama model (or set `QUACKULA_MODEL`); a coder model like `qwen2.5-coder:7b` gives sharper fixes |
| `--fast` | skip the typewriter and dramatic pauses |
| `--offline` | no model at all; the duck uses its canned ancient wisdom |
| `--cpu` | force CPU inference (Quackula also falls back automatically if the GPU backend crashes) |

## Why open-weight / local

- **Your code is private.** A tool that reads every cursed corner of your
  company's codebase shouldn't send it to someone else's server. Local inference
  makes it safe to point at real work code.
- **Works with the lights (and the Wi-Fi) off.** No API key, no account, no
  network. With `--offline` it even works without a model.
- **Costs nothing to run.** Exorcise as often as you like; no per-token bill.
- **Swap the spirit.** Change one flag to channel a different model, or edit the
  `PERSONA` string to summon a different ghost entirely.
- **Runs on old hardware.** Built and tested on a GTX 1060 whose driver is too
  old for Ollama's CUDA backend, so Quackula detects the crash and channels
  through the CPU instead.

## How it works

1. Static scanning (Python `ast` for `.py`, regex and brace matching for C-like
   languages) finds and ranks curses by severity.
2. For each curse, Quackula sends the cursed lines, surrounding context, and the
   *known cure* to the local model. Grounding a small 4B model with the cure keeps
   its advice correct while the persona supplies the drama.
3. Replies stream back token by token through a typewriter effect, with
   flickering zalgo chants between curses.
