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
    token_path: str = "config/oauth_tokens.json"
    scopes: list[str] = field(default_factory=lambda: [
        "sme-company-file",
        "sme-general-ledger",
        "sme-sales",
        "sme-purchases",
        "sme-banking",
        "sme-contacts-customer",
        "sme-contacts-supplier",
    ])


def _get_project_root() -> Path:
    """Walk up from this file to find the directory containing pyproject.toml."""
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


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
    project_root = _get_project_root()

    config_path_str = os.environ.get("MYOB_MCP_CONFIG")
    if config_path_str:
        config_path = Path(config_path_str)
    else:
        config_path = project_root / "config" / "config.json"

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

    # Resolve token_path relative to project root
    token_path = data.get("token_path", "config/oauth_tokens.json")
    resolved_token_path = str(project_root / token_path)

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
        ]),
    )

    if not config.client_id or not config.client_secret:
        raise ValueError(
            "MYOB_CLIENT_ID and MYOB_CLIENT_SECRET must be set "
            "(via config.json or environment variables)"
        )

    return config
