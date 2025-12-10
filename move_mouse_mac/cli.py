"""Small macOS helper that jiggles the mouse to keep remote sessions awake."""

import argparse
import logging
import os
import random
import signal
import threading
import time
from typing import Any, Tuple

try:
    import Quartz as _Quartz  # type: ignore[import]
except ImportError as exc:
    raise SystemExit(
        "Quartz framework not found. Install with 'uv add pyobjc-framework-Quartz' or 'pip install pyobjc-framework-Quartz'."
    ) from exc

Quartz: Any = _Quartz


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for cursor movement configuration."""
    parser = argparse.ArgumentParser(
        description="Move the macOS cursor randomly until the user touches the mouse/trackpad."
    )
    parser.add_argument(
        "--start-delay",
        type=float,
        default=10.0,
        help="Seconds to wait before starting cursor movement.",
    )
    parser.add_argument(
        "--min-interval",
        type=float,
        default=3.0,
        help="Minimum seconds between moves.",
    )
    parser.add_argument(
        "--max-interval",
        type=float,
        default=7.0,
        help="Maximum seconds between moves.",
    )
    parser.add_argument(
        "--max-jitter",
        type=int,
        default=120,
        help="Maximum pixels to move from the current position on each axis.",
    )
    return parser.parse_args()


def setup_logging() -> None:
    """Configure basic logging for the script."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def get_screen_bounds() -> Tuple[int, int]:
    """Return the width and height of the main display in pixels."""
    display_id = Quartz.CGMainDisplayID()
    return Quartz.CGDisplayPixelsWide(display_id), Quartz.CGDisplayPixelsHigh(
        display_id
    )


def get_cursor_position() -> Tuple[float, float]:
    """Get the current cursor position in screen coordinates."""
    event = Quartz.CGEventCreate(None)
    location = Quartz.CGEventGetLocation(event)
    return location.x, location.y


def clamp_position(x: float, y: float, width: int, height: int) -> Tuple[float, float]:
    """Clamp the target coordinates so they stay within the screen bounds."""
    return max(0, min(x, width - 1)), max(0, min(y, height - 1))


def create_mouse_event(x: float, y: float) -> Any:
    """Create a mouse-move event at the provided coordinates."""
    event = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventMouseMoved, (x, y), Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventSetIntegerValueField(
        event, Quartz.kCGEventSourceUnixProcessID, os.getpid()
    )
    return event


def wait_with_checks(duration: float, stop_event: threading.Event) -> bool:
    """Sleep up to duration, returning True early if stop_event becomes set."""
    deadline = time.time() + duration
    while time.time() < deadline:
        if stop_event.is_set():
            return True
        time.sleep(0.1)
    return stop_event.is_set()


def user_activity_listener(
    stop_event: threading.Event, user_event: threading.Event
) -> None:
    """Listen for real user mouse activity and set user_event when detected."""
    pid = os.getpid()

    def _callback(_proxy, _event_type, event, _refcon):
        # Explicitly mark unused parameters for linters.
        del _proxy, _event_type, _refcon
        source_pid = Quartz.CGEventGetIntegerValueField(
            event, Quartz.kCGEventSourceUnixProcessID
        )
        if source_pid != pid:
            logging.info(
                "Detected user input from PID %s; stopping movement.", source_pid
            )
            user_event.set()
        return event

    event_mask = (
        Quartz.CGEventMaskBit(Quartz.kCGEventMouseMoved)
        | Quartz.CGEventMaskBit(Quartz.kCGEventLeftMouseDown)
        | Quartz.CGEventMaskBit(Quartz.kCGEventRightMouseDown)
        | Quartz.CGEventMaskBit(Quartz.kCGEventOtherMouseDown)
        | Quartz.CGEventMaskBit(Quartz.kCGEventScrollWheel)
    )

    tap = Quartz.CGEventTapCreate(
        Quartz.kCGHIDEventTap,
        Quartz.kCGHeadInsertEventTap,
        Quartz.kCGEventTapOptionDefault,
        event_mask,
        _callback,
        None,
    )

    if not tap:
        logging.error(
            "Unable to create event tap. Grant Accessibility permissions and try again."
        )
        user_event.set()
        return

    run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
    Quartz.CFRunLoopAddSource(
        Quartz.CFRunLoopGetCurrent(), run_loop_source, Quartz.kCFRunLoopDefaultMode
    )
    Quartz.CGEventTapEnable(tap, True)

    while not stop_event.is_set():
        Quartz.CFRunLoopRunInMode(Quartz.kCFRunLoopDefaultMode, 0.25, True)

    Quartz.CFRunLoopRemoveSource(
        Quartz.CFRunLoopGetCurrent(), run_loop_source, Quartz.kCFRunLoopDefaultMode
    )
    Quartz.CFMachPortInvalidate(tap)


def move_cursor_randomly(args: argparse.Namespace) -> None:
    """Move the cursor randomly until user activity is detected or interrupted."""
    width, height = get_screen_bounds()
    user_activity = threading.Event()
    stop_listener = threading.Event()

    listener_thread = threading.Thread(
        target=user_activity_listener, args=(stop_listener, user_activity), daemon=True
    )
    listener_thread.start()

    logging.info(
        "Waiting %.1f seconds before starting cursor movement.", args.start_delay
    )
    start_deadline = time.time() + args.start_delay
    while time.time() < start_deadline:
        # Ignore user input during the initial delay window.
        time.sleep(0.1)
    if user_activity.is_set():
        logging.info(
            "User input detected during startup delay; ignoring and continuing."
        )
        user_activity.clear()

    logging.info(
        "Starting cursor movement with intervals between %.1f and %.1f seconds.",
        args.min_interval,
        args.max_interval,
    )

    try:
        while not user_activity.is_set():
            current_x, current_y = get_cursor_position()
            dx = random.randint(-args.max_jitter, args.max_jitter)
            dy = random.randint(-args.max_jitter, args.max_jitter)
            target_x, target_y = clamp_position(
                current_x + dx, current_y + dy, width, height
            )

            logging.info(
                "Moving cursor from (%.0f, %.0f) to (%.0f, %.0f).",
                current_x,
                current_y,
                target_x,
                target_y,
            )

            event = create_mouse_event(target_x, target_y)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

            interval = random.uniform(args.min_interval, args.max_interval)
            if wait_with_checks(interval, user_activity):
                break
    except KeyboardInterrupt:
        logging.info("Keyboard interrupt received; stopping.")
    finally:
        stop_listener.set()
        listener_thread.join(timeout=1)
        logging.info("Cursor movement stopped.")


def main() -> None:
    """Entry point: parse arguments, configure logging, and start cursor movement."""
    # Allow Ctrl+C to terminate immediately even when imported via a wrapper.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    args = parse_args()
    setup_logging()

    if args.min_interval > args.max_interval:
        raise ValueError("min-interval cannot be greater than max-interval.")

    move_cursor_randomly(args)


if __name__ == "__main__":
    # Allow Ctrl+C to terminate immediately.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    main()
