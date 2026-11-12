import json
import os
import tempfile
from pathlib import Path

from .record_manager import RecordManager


def _check_path(path):
    path = Path(path)
    if path.suffix.lower() != ".pim":
        raise ValueError("Storage files must use the .pim extension.")
    return path


def _validate_snapshot(data):
    if not isinstance(data, dict) or not isinstance(data.get("records"), list):
        raise ValueError("Expected a list of records in the .pim file.")
    if not data["records"]:
        raise ValueError("The .pim file must contain at least one record.")

    validator = RecordManager()
    validator.replace_snapshot(data)


def save_records(record_manager, path):
    """Save a validated record-manager snapshot to a .pim JSON file."""
    path = _check_path(path)
    data = record_manager.snapshot()
    _validate_snapshot(data)

    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(data, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def load_records(record_manager, path):
    """Load a validated .pim JSON snapshot without changing state on failure."""
    path = _check_path(path)
    try:
        with path.open(encoding="utf-8") as source:
            data = json.load(source)
    except RecursionError as error:
        raise ValueError("The .pim file contains excessively nested data.") from error
    except json.JSONDecodeError as error:
        raise ValueError("The .pim file does not contain valid JSON.") from error

    _validate_snapshot(data)
    record_manager.replace_snapshot(data)