## Mouse mover for macOS

Python helper that jiggles the cursor so a remote/VM session stays awake. It ignores user input during an initial delay window, then moves the mouse in small random steps until it sees real user input, at which point it stops immediately.

### How it works

- Waits for `--start-delay` seconds (defaults to 10) and ignores any mouse activity during that window so setup clicks don't stop it.
- Spawns an event tap via Quartz to monitor real mouse/trackpad activity. Events from other processes are treated as user activity; events sourced from this script are ignored.
- On each cycle, it randomly offsets the cursor by up to `--max-jitter` pixels on both axes, sleeps a random interval between `--min-interval` and `--max-interval`, and logs every move with timestamps.
- Stops when:
  - Mouse/trackpad input is detected from another PID (you moved it), or
  - You hit `Ctrl+C`.

### Requirements

- macOS (tested on Apple Silicon)
- Python 3.12+
- Accessibility permission for the terminal running the script (System Settings -> Privacy & Security -> Accessibility)
- Quartz bindings (managed via uv by default)

### Install (preferred: uv)

1. Clone the repo and enter it.
2. Sync dependencies: `uv sync`
3. If Quartz is missing, add it: `uv add pyobjc-framework-Quartz`

### Install (optional: pip)

If you prefer pip/venv:

- `python -m venv .venv && source .venv/bin/activate`
- `pip install pyobjc-framework-Quartz`

### Run (uv)

```
uv run main.py --start-delay 10 --min-interval 3 --max-interval 7 --max-jitter 120
```

With plain python:

```
python main.py --start-delay 10 --min-interval 3 --max-interval 7 --max-jitter 120
```

Flags:

- `--start-delay`: wait time before cursor movement begins (seconds).
- `--min-interval` / `--max-interval`: range for random sleep between moves (seconds).
- `--max-jitter`: max pixels to move from the current cursor position on each axis.
