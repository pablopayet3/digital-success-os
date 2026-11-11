"""Load the YAML files in config/. Synthetic data, fictional company."""

import yaml

from common.paths import CONFIG_DIR


def load_yaml(name: str) -> dict:
    """Read one config file, for example load_yaml("rollout.yaml")."""
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _merge(base: dict, override: dict) -> dict:
    """Return base with override laid on top, going into nested sections."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_world_config(profile: str | None = None) -> dict:
    """Read config/world.yaml. A profile (for example "small") overrides the defaults."""
    cfg = load_yaml("world.yaml")
    profiles = cfg.pop("profiles", {})
    if profile:
        cfg = _merge(cfg, profiles[profile])
    return cfg
