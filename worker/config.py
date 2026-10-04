"""Paths, environment variables and YAML config loading."""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"

load_dotenv(ROOT / ".env")


def env(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise RuntimeError(f"{key} is missing from .env — run: python3 scripts/setup_env.py")
    return value


def path_from_env(key: str) -> Path:
    path = Path(env(key))
    return path if path.is_absolute() else ROOT / path


def load_yaml(name: str) -> dict:
    """Load config/<name>.yaml, falling back to config/<name>.example.yaml."""
    for candidate in (CONFIG_DIR / f"{name}.yaml", CONFIG_DIR / f"{name}.example.yaml"):
        if candidate.exists():
            return yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
    raise FileNotFoundError(f"config/{name}.yaml not found")
