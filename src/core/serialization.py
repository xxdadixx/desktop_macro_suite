from pathlib import Path
from typing import Final, cast

import yaml

from .ast import MacroSequence
from .exceptions import SchemaVersionMismatchError, SerializationError

CURRENT_SCHEMA_VERSION: Final[str] = "1.0.0"
SUPPORTED_SCHEMA_VERSIONS: Final[frozenset[str]] = frozenset({CURRENT_SCHEMA_VERSION})

__all__: Final[list[str]] = [
    "CURRENT_SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "MacroSerializer",
    "load_macro_file",
    "macro_from_json",
    "macro_from_yaml",
    "macro_to_json",
    "macro_to_yaml",
    "save_macro_file",
]


def _validate_schema_version(sequence: MacroSequence) -> None:
    if sequence.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise SchemaVersionMismatchError(
            expected_version=CURRENT_SCHEMA_VERSION,
            actual_version=sequence.schema_version,
        )


def macro_to_json(sequence: MacroSequence, *, indent: int = 2) -> str:
    _validate_schema_version(sequence)
    try:
        return sequence.model_dump_json(indent=indent)
    except Exception as err:
        raise SerializationError(f"Failed to serialize macro to JSON: {err}") from err


def macro_from_json(json_content: str) -> MacroSequence:
    try:
        sequence = MacroSequence.model_validate_json(json_content)
    except ValueError as err:
        raise SerializationError(
            f"Failed to deserialize macro from JSON: {err}"
        ) from err

    _validate_schema_version(sequence)
    return sequence


def macro_to_yaml(sequence: MacroSequence) -> str:
    _validate_schema_version(sequence)
    try:
        data: dict[str, object] = sequence.model_dump(mode="json")
        dumped: str = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        return dumped
    except yaml.YAMLError as err:
        raise SerializationError(f"Failed to format macro to YAML: {err}") from err
    except Exception as err:
        raise SerializationError(f"Failed to serialize macro to YAML: {err}") from err


def macro_from_yaml(yaml_content: str) -> MacroSequence:
    try:
        raw_data: object = cast(object, yaml.safe_load(yaml_content))
    except yaml.YAMLError as err:
        raise SerializationError(f"Malformed YAML content: {err}") from err

    if not isinstance(raw_data, dict):
        raise SerializationError(
            f"Expected top-level mapping in YAML, received: {type(raw_data).__name__}"
        )

    try:
        sequence = MacroSequence.model_validate(raw_data)
    except ValueError as err:
        raise SerializationError(f"Failed to validate macro from YAML: {err}") from err

    _validate_schema_version(sequence)
    return sequence


def save_macro_file(sequence: MacroSequence, file_path: str | Path) -> None:
    path = Path(file_path)
    extension = path.suffix.lower()

    if extension == ".json":
        serialized = macro_to_json(sequence)
    elif extension in {".yaml", ".yml"}:
        serialized = macro_to_yaml(sequence)
    else:
        raise SerializationError(
            f"Unsupported file format '{extension}'. Use .json, .yaml, or .yml"
        )

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialized, encoding="utf-8")
    except OSError as err:
        raise SerializationError(f"Failed to write macro file '{path}': {err}") from err


def load_macro_file(file_path: str | Path) -> MacroSequence:
    path = Path(file_path)

    if not path.is_file():
        raise SerializationError(f"File not found: '{path}'")

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as err:
        raise SerializationError(f"Failed to read file '{path}': {err}") from err

    extension = path.suffix.lower()
    if extension == ".json":
        return macro_from_json(content)
    if extension in {".yaml", ".yml"}:
        return macro_from_yaml(content)

    raise SerializationError(
        f"Unsupported file format '{extension}'. Use .json, .yaml, or .yml"
    )


class MacroSerializer:
    """Facade for MacroSequence serialization and filesystem persistence."""

    @staticmethod
    def to_json(sequence: MacroSequence, *, indent: int = 2) -> str:
        return macro_to_json(sequence, indent=indent)

    @staticmethod
    def from_json(json_content: str) -> MacroSequence:
        return macro_from_json(json_content)

    @staticmethod
    def to_yaml(sequence: MacroSequence) -> str:
        return macro_to_yaml(sequence)

    @staticmethod
    def from_yaml(yaml_content: str) -> MacroSequence:
        return macro_from_yaml(yaml_content)

    @staticmethod
    def save_to_file(sequence: MacroSequence, file_path: str | Path) -> None:
        save_macro_file(sequence, file_path)

    @staticmethod
    def load_from_file(file_path: str | Path) -> MacroSequence:
        return load_macro_file(file_path)