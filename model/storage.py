"""Part D: save and load records as .pim files (UTF-8 JSON)."""

import json
import os
import tempfile
from pathlib import Path
from typing import Union

from .record_manager import RecordManager

PathLike = Union[str, "os.PathLike[str]"]


def _check_path(path: PathLike) -> Path:
    path = Path(path)
    if path.suffix.lower() != ".pim":
        raise ValueError("Storage files must use the .pim extension.")
    return path


def save_records(record_manager: RecordManager, path: PathLike) -> None:
    """Save all records to a .pim file. The write is atomic: on failure the old file is kept.

    Raises:
        ValueError: the path does not end in .pim.
        OSError: the file cannot be written.
    """
    path = _check_path(path)
    data = record_manager.snapshot()

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


def load_records(record_manager: RecordManager, path: PathLike) -> None:
    """Replace all records with those in a .pim file. On any failure the records are unchanged.

    Raises:
        ValueError: the path does not end in .pim, or the file is not valid PIM data
            (bad JSON, bad encoding, malformed or invalid records).
        OSError: the file cannot be read.
    """
    path = _check_path(path)
    try:
        with path.open(encoding="utf-8") as source:
            data = json.load(source)
    except RecursionError as error:
        raise ValueError("The .pim file contains excessively nested data.") from error
    except json.JSONDecodeError as error:
        raise ValueError("The .pim file does not contain valid JSON.") from error

    record_manager.replace_snapshot(data)