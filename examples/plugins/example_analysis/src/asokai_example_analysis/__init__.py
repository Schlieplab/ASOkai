"""Package metadata exposed to ASOkai plugin discovery."""

from pathlib import Path


CONFIG_SCHEMA_PATH = Path(__file__).with_name("config.schema.yaml")

__all__ = ["CONFIG_SCHEMA_PATH"]
