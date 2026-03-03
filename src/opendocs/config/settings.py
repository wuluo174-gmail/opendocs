"""Settings models and loading helpers."""

from __future__ import annotations

from pathlib import Path
import os
import platform
import tomllib

from pydantic import BaseModel, Field, ValidationError

from opendocs.exceptions import ConfigError


class AppSettings(BaseModel):
    language: str = "zh-CN"
    output_dir: str = "OpenDocs_Output"
    local_only: bool = True


class IndexSettings(BaseModel):
    watch_changes: bool = True
    chunk_size_chars: int = 900
    chunk_overlap_ratio: float = 0.12


class RetrievalSettings(BaseModel):
    top_k: int = 12
    fts_weight: float = 0.55
    dense_weight: float = 0.35
    freshness_weight: float = 0.10


class MemorySettings(BaseModel):
    m1_ttl_days: int = 30
    m2_enabled: bool = False


class ProviderSettings(BaseModel):
    default_mode: str = "local"
    llm_provider: str = "ollama"
    embedding_provider: str = "local"


class OpenDocsSettings(BaseModel):
    app: AppSettings = Field(default_factory=AppSettings)
    index: IndexSettings = Field(default_factory=IndexSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    provider: ProviderSettings = Field(default_factory=ProviderSettings)


def get_user_data_dir() -> Path:
    system = platform.system().lower()
    if system == "windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "OpenDocs"
    elif system == "darwin":
        return Path.home() / "Library" / "Application Support" / "OpenDocs"

    return Path.home() / ".local" / "share" / "OpenDocs"


def default_settings_path() -> Path:
    return get_user_data_dir() / "config" / "settings.toml"


def load_settings(config_path: str | Path | None = None) -> OpenDocsSettings:
    env_override = os.environ.get("OPENDOCS_CONFIG")
    has_explicit_path = config_path is not None
    has_env_override = bool(env_override)
    resolved = Path(config_path or env_override or default_settings_path())

    if not resolved.exists():
        if has_explicit_path or has_env_override:
            raise ConfigError(f"config path does not exist: {resolved}")
        return OpenDocsSettings()

    try:
        with resolved.open("rb") as fh:
            data = tomllib.load(fh)
        return OpenDocsSettings.model_validate(data)
    except (OSError, tomllib.TOMLDecodeError, ValidationError) as exc:
        raise ConfigError(f"failed to load config from {resolved}: {exc}") from exc
