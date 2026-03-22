"""Shared loader for retrieval stage assets.

This keeps runtime asset reads aligned with the same asset refs used in
acceptance provenance and stage reports.
"""

from __future__ import annotations

from importlib.resources import files
from pathlib import PurePosixPath

STAGE_ASSET_ROOT_REF = PurePosixPath("src/opendocs/retrieval/assets")


def read_stage_asset_text(asset_ref: str, *, encoding: str = "utf-8") -> str:
    relative_path = stage_asset_relative_path(asset_ref)
    resource = files("opendocs.retrieval.assets").joinpath(str(relative_path))
    return resource.read_text(encoding=encoding)


def stage_asset_relative_path(asset_ref: str) -> PurePosixPath:
    asset_path = PurePosixPath(asset_ref)
    try:
        relative_path = asset_path.relative_to(STAGE_ASSET_ROOT_REF)
    except ValueError as exc:
        raise ValueError(f"unsupported retrieval stage asset ref: {asset_ref!r}") from exc
    if not relative_path.parts:
        raise ValueError(f"retrieval stage asset ref must point to a file: {asset_ref!r}")
    if any(part in {"..", "."} for part in relative_path.parts):
        raise ValueError(f"retrieval stage asset ref must stay within asset root: {asset_ref!r}")
    return relative_path
