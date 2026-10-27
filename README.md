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

## See it in action

### In the terminal

An exorcism opens with the duck rising from the bathwater, then a summary of
what it found before the ritual begins:

![Terminal running "python quackula.py exorcise haunted_sample". An ASCII-art duck and the title QUACKULA appear, followed by: files sniffed 2, curses detected 13, and a red bar showing 100% possession level. A list counts each curse type: The Unkept Promise x4, The Silent Scream x3, The Whispering Logs x2, The Abyss of Indentation x2, The Commented Corpse x1, The Eldritch Function x1. Below, curse 1 of 5, The Abyss of Indentation in legacy_payments.py line 20, eight levels deep, shows the cursed lines, the chant "In nomine Linus, et Guido, et Spiritus Stack Overflow...", and the status "the duck is channeling...".](pics/Capture1.PNG)

Each curse gets a chant in red, then the duck's verdict streams in (in cyan),
typewriter style: what evil the curse causes, how to lift it, and an ominous
closing line. Now and then the duck drifts off to complain about the afterlife.

![Terminal output from the middle of an exorcism. Under the chant "Quack quack... VADE RETRO!", the duck explains that The Silent Scream swallows errors and that the fix is to log them. Curse 3 of 5, The Unkept Promise in legacy_payments.py line 10, shows a "HACK: don't touch, nobody knows why it works" comment and the duck's advice to turn it into a real ticket or remove it, followed by the aside "The candle flickers. The duck pretends that was intentional." Curse 4 of 5, The Eldritch Function, a 46-line process_payment function, begins below.](pics/Capture2.PNG)

When the ritual ends, Quackula tells you how many lesser curses are still
lurking and the exact flag to deal with them all:

![The end of an exorcism. The duck explains that The Whispering Logs are leftover console.log calls that should be removed, mutters "No bathtubs in the beyond. Not one.", then announces "THE RITUAL IS COMPLETE" and "8 lesser curses still lurk. Run me again with --max 13 if you dare."](pics/Capture3.PNG)

### In the browser

The séance room shows the same scan as a dashboard: files sniffed, curses
detected, a possession meter, and a count of each curse type. Every curse is a
card with its location, severity (one to three skulls) and the cursed lines,
plus an **Exorcise** button. **Perform the ritual** exorcises the worst few in
order, and **Download report** saves the results as Markdown. The bar at the
top picks the model and toggles Offline, CPU only and Theatrics, and the
**CLI equivalent** line always shows the matching command to copy.

![The Quackula web UI in a browser at 127.0.0.1:8666, dark purple theme. The settings bar shows model gemma3:4b with Offline, CPU only and Theatrics checked, and a status of "offline: canned ancient wisdom". The Exorcise tab has a folder path, a "Sniff for curses" button, and the CLI equivalent "python quackula.py exorcise C:\Users\macla\workspace\ghost_in_the_machine --offline --cpu" with a Copy button. Results: 4 files sniffed, 19 curses detected, 100% possession level, and chips counting each curse type. Below are an "Exorcise the worst 5" field, a "Perform the ritual" button, a "Download report" button, and curse cards for The Abyss of Indentation (quackula.py line 448, 8 levels deep) and The Eldritch Function (quackula.py line 532, 84 lines), each with its code snippet and an Exorcise button.](pics/Capture5.PNG)

The **Séance (debug)** tab is rubber-duck debugging as a chat. Optionally give
the duck a file to read first, then describe what's wrong. The duck won't hand
you the answer: it asks sharp questions and suggests what to check, so you
find the bug yourself (with the occasional complaint about ectoplasm).
**New séance** starts a fresh conversation.

![The Séance (debug) tab of the Quackula web UI. The status reads "the spirit of gemma3:4b is listening", with CPU only and Theatrics checked. The file field holds haunted_sample/legacy_payments.py, and the CLI equivalent line shows "python quackula.py debug --file" with that path and "--cpu". In the chat, the duck greets "Ah. A mortal with a bug. Sit. Speak. The duck is listening." The user writes "It is throwing me errors". The duck replies, asking what specific error the process_payment function gives and asking to see the entire traceback, not just the last line, then complains that the ectoplasm is making it dizzy. A message box and a Speak button sit at the bottom.](pics/Capture6.PNG)

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
