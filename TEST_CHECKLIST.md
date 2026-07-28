# Genesis — First Test Session Checklist

Run `update_genesis.bat`, then `setup_dependencies.bat` (once), then
`launch_genesis.bat`.

## Basics (first 2 minutes)
- [ ] Desktop window opens: chat left, live graphs center, sliders right.
      **If the window fails to open** (PyQt6 issue on your machine), the
      terminal UI is the fallback and has every feature:
      `cd project-genesis && python src\ui.py --resume --self-directed`
- [ ] Cycles/sec graph moves; status bar shows `cycle N · ... · N/s`
- [ ] Drag the Speed slider to 10 — cycles/sec should climb; CPU visible
- [ ] Type `hello` — reply within a few seconds (during a web fetch you may
      see "mid web-read", it should clear within ~30s, not hang forever)

## New abilities to try (in chat)
- [ ] `remember to learn about volcanoes` → it should say it's now a goal
- [ ] `what are your goals?` → lists volcanoes
- [ ] `what have you been deciding?` → real topics it chose, with reasons
- [ ] `where did you learn about <topic it read>?` → sources + trust scores
- [ ] `what do you value?` → early on, honestly: "I haven't lived enough to
      hold values yet." Values form only after real reading + reflection.
- [ ] Drop a `.wav` path in chat as `learn` won't do it — instead audio goes
      through the API for now; or just verify text learning first.

## Overnight test (the real one)
Leave it running self-directed overnight, then check:
- [ ] `status` — memories and associations grew; wanting is NOT stuck at 0
- [ ] `what have you been deciding?` — a night of its own choices
- [ ] `what do you value?` — first authored values may appear
- [ ] Close and relaunch: `what are your goals?` — volcanoes survived

## If something breaks
- Quit cleanly with `quit` (it saves; force-closing can lose ~2 min)
- Errors are logged, not fatal — tell Claude Code what you saw and when
