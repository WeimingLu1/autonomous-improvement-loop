"""
YAML configuration loader for ail.
Reads .ail/config.yaml and merges with hardcoded defaults.
"""

from __future__ import annotations

from pathlib import Path


# ── Constants (local, no external imports) ─────────────────────────────────────

DEFAULT_SCHEDULE_MS = 30 * 60 * 1000   # 30 min
DEFAULT_TIMEOUT_S = 3600                # 1 hour
DEFAULT_LANGUAGE = "en"


# ── Config loader ─────────────────────────────────────────────────────────────

def load_config(project: Path | None = None) -> dict:
    """
    Load ail configuration from .ail/config.yaml.

    Returns a dict of config values.  If config.yaml does not exist
    or cannot be parsed, returns the hardcoded defaults.
    """
    defaults: dict[str, object] = {
        "schedule_ms": DEFAULT_SCHEDULE_MS,
        "timeout_s": DEFAULT_TIMEOUT_S,
        "sticky_threshold": 3,
        "git_since_days": 90,
        "git_log_timeout": 10,
        "git_log_name_only_timeout": 15,
        "detect_timeout": 5,
        "trigger_timeout_s": 300,
        "file_lock_timeout": 30.0,
        "language": DEFAULT_LANGUAGE,
        "i18n_default_lang": "zh",
    }

    if project is None:
        project = Path.cwd()

    config_path = project / ".ail" / "config.yaml"
    if not config_path.exists():
        return defaults

    try:
        import yaml
        with open(config_path, encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        # Merge: explicit values override defaults
        result = dict(defaults)
        for key, value in data.items():
            if key in defaults:
                result[key] = value
        return result
    except Exception:
        # YAML parse error or other failure — fall back to defaults
        return defaults
