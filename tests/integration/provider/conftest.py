"""Provider integration test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from opendocs.provider.base import PrivacyMode
from opendocs.provider.mock import MockProvider
from opendocs.provider.service import ProviderService
from opendocs.storage.db import build_sqlite_engine, init_db


@pytest.fixture()
def provider_engine(tmp_path: Path) -> Engine:
    db_path = tmp_path / "provider_test.db"
    init_db(db_path)
    return build_sqlite_engine(db_path)


@pytest.fixture()
def local_service(provider_engine: Engine) -> ProviderService:
    """ProviderService in LOCAL mode with mock provider only."""
    return ProviderService(
        mode=PrivacyMode.LOCAL,
        providers={"mock": MockProvider()},
        active_name="mock",
        engine=provider_engine,
    )
