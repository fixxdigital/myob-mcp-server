from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class MyobConfig:
    client_id: str
    client_secret: str
    redirect_uri: str = "http://localhost:33333/callback"
    default_company_file_id: str = ""
    token_path: str = "oauth_tokens.json"
    scopes: list[str] = field(default_factory=lambda: [
        "sme-company-file",
        "sme-general-ledger",
        "sme-sales",
        "sme-purchases",
        "sme-banking",
        "sme-contacts-customer",
        "sme-contacts-supplier",
        "sme-contacts-employee",
    ])


def _get_config_home() -> Path:
    """Return the configuration directory, searching multiple locations.

    Search order:
      1. $MYOB_MCP_CONFIG env var (parent directory of the specified file)
      2. ./config/config.json relative to CWD (running from project clone)
      3. Platform user config dir (~/.config/myob-mcp or %APPDATA%/myob-mcp)
    """
    env = os.environ.get("MYOB_MCP_CONFIG")
    if env:
        return Path(env).resolve().parent

    cwd_config = Path.cwd() / "config" / "config.json"
    if cwd_config.exists():
        return cwd_config.parent

    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", "~")).expanduser()
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser()
    user_dir = base / "myob-mcp"
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def _substitute_env_vars(obj: object) -> object:
    """Recursively replace ${ENV_VAR} patterns in strings with env var values."""
    if isinstance(obj, str):
        return re.sub(
            r"\$\{(\w+)\}",
            lambda m: os.environ.get(m.group(1), m.group(0)),
            obj,
        )
    if isinstance(obj, dict):
        return {k: _substitute_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute_env_vars(v) for v in obj]
    return obj


def load_config() -> MyobConfig:
    """Load configuration from JSON file or environment variables."""
    config_home = _get_config_home()

    config_path_str = os.environ.get("MYOB_MCP_CONFIG")
    if config_path_str:
        config_path = Path(config_path_str)
    else:
        cwd_config = Path.cwd() / "config" / "config.json"
        user_config = config_home / "config.json"
        config_path = cwd_config if cwd_config.exists() else user_config

    if config_path.exists():
        logger.info("Loading config from %s", config_path)
        with open(config_path) as f:
            raw = json.load(f)
        data = _substitute_env_vars(raw)
    else:
        logger.info("No config file found, using environment variables")
        data = {
            "client_id": os.environ.get("MYOB_CLIENT_ID", ""),
            "client_secret": os.environ.get("MYOB_CLIENT_SECRET", ""),
        }

    # Resolve token_path relative to config home directory
    token_path = data.get("token_path", "oauth_tokens.json")
    token_path_obj = Path(token_path)
    if token_path_obj.is_absolute():
        resolved_token_path = str(token_path_obj)
    else:
        resolved_token_path = str(config_home / token_path)

    config = MyobConfig(
        client_id=data.get("client_id", ""),
        client_secret=data.get("client_secret", ""),
        redirect_uri=data.get("redirect_uri", "http://localhost:33333/callback"),
        default_company_file_id=data.get("default_company_file_id", ""),
        token_path=resolved_token_path,
        scopes=data.get("scopes", [
            "sme-company-file",
            "sme-general-ledger",
            "sme-sales",
            "sme-purchases",
            "sme-banking",
            "sme-contacts-customer",
            "sme-contacts-supplier",
            "sme-contacts-employee",
        ]),
    )

    if not config.client_id or not config.client_secret:
        raise ValueError(
            "MYOB_CLIENT_ID and MYOB_CLIENT_SECRET must be set "
            "(via config.json or environment variables)"
        )

    return config
