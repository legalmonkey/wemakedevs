"""Configuration loader with JSON Schema validation (Part A, Phase A0).

Strict adherence to Section 0 rules:
- Rule 3: Zero hardcoding in code. Instances and policies supplied via validated YAML configs.
- Exit Check: Invalid config is rejected with a clear, descriptive message.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Optional, Union
import yaml
import jsonschema
from jsonschema.exceptions import ValidationError


class ConfigValidationError(Exception):
    """Raised when configuration fails JSON Schema validation."""
    pass


class ConfigLoader:
    """Loads and validates project YAML configuration files against JSON Schemas."""

    def __init__(self, project_root: Optional[Union[str, Path]] = None) -> None:
        if project_root is None:
            self.project_root = Path(__file__).resolve().parent.parent
        else:
            self.project_root = Path(project_root).resolve()
        self.schemas_dir = self.project_root / "config" / "schemas"

    def load_yaml(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Loads a YAML file from disk."""
        target = Path(file_path)
        if not target.is_absolute():
            target = self.project_root / target

        if not target.exists():
            raise FileNotFoundError(f"Configuration file not found: {target}")

        with open(target, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if data is None:
            return {}
        if not isinstance(data, dict):
            raise ConfigValidationError(
                f"Configuration at {target} must be a dictionary/mapping, got {type(data).__name__}"
            )
        return data

    def validate(self, config_data: Dict[str, Any], schema_path: Union[str, Path]) -> None:
        """Validates configuration dictionary against a JSON Schema file."""
        target_schema = Path(schema_path)
        if not target_schema.is_absolute():
            target_schema = self.schemas_dir / target_schema

        if not target_schema.exists():
            raise FileNotFoundError(f"JSON schema not found: {target_schema}")

        with open(target_schema, "r", encoding="utf-8") as f:
            schema = yaml.safe_load(f)

        validator = jsonschema.Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(config_data), key=lambda e: e.path)

        if errors:
            details = []
            for err in errors:
                loc = " -> ".join([str(p) for p in err.path]) if err.path else "root"
                details.append(f"Field '{loc}': {err.message} (invalid value: {err.instance!r})")
            error_message = (
                f"Configuration validation failed against schema '{target_schema.name}':\n"
                + "\n".join(f"  - {d}" for d in details)
            )
            raise ConfigValidationError(error_message)

    def load_and_validate(
        self,
        yaml_path: Union[str, Path],
        schema_path: Union[str, Path],
    ) -> Dict[str, Any]:
        """Loads YAML config and validates it against specified JSON schema."""
        data = self.load_yaml(yaml_path)
        self.validate(data, schema_path)
        return data

    def load_gates(self, gates_yaml_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
        """Loads and validates gates.yaml against gates.schema.json."""
        target = gates_yaml_path or (self.project_root / "config" / "gates.yaml")
        return self.load_and_validate(target, self.schemas_dir / "gates.schema.json")

    def load_policy(self, policy_yaml_path: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
        """Loads and validates policy.yaml against policy.schema.json."""
        target = policy_yaml_path or (self.project_root / "config" / "policy.yaml")
        return self.load_and_validate(target, self.schemas_dir / "policy.schema.json")

    def load_ontology(self, ontology_yaml_path: Union[str, Path]) -> Dict[str, Any]:
        """Loads and validates an ontology YAML against ontology.schema.json."""
        return self.load_and_validate(ontology_yaml_path, self.schemas_dir / "ontology.schema.json")
