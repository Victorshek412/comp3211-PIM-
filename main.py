"""Start the PIM terminal: python3 main.py"""
from controller import Controller
from model.record_manager import RecordManager


def main() -> int:
    """Run the PIM until the user exits and return the exit code."""
    return Controller(RecordManager()).run()


if __name__ == "__main__":
    raise SystemExit(main())
