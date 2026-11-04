"""Workspace-scoped object storage. Keys are `ws/{workspace_id}/…`; only local disk ships (plan A9)."""
import os
import tempfile
from pathlib import Path
from typing import Protocol

from django.conf import settings

from .context import RequestContext


class StorageKeyError(ValueError):
    """The key is malformed or belongs to another workspace."""


class StoragePort(Protocol):
    def put(self, ctx: RequestContext, key: str, data: bytes) -> None: ...

    def get(self, ctx: RequestContext, key: str) -> bytes: ...

    def delete(self, ctx: RequestContext, key: str) -> None: ...


def storage_key(ctx: RequestContext, *parts: str) -> str:
    return "/".join(("ws", str(ctx.workspace_id), *parts))


class LocalFileStorage:
    def __init__(self, root: Path | str) -> None:
        self._root = Path(root)

    def _path(self, ctx: RequestContext, key: str) -> Path:
        segments = key.split("/")
        if segments[:2] != ["ws", str(ctx.workspace_id)] or len(segments) < 3:
            raise StorageKeyError("the key is outside this workspace")
        if any(part in ("", ".", "..") or "\\" in part or "\x00" in part for part in segments):
            raise StorageKeyError("the key is malformed")
        workspace_root = self._root.resolve() / "ws" / str(ctx.workspace_id)
        path = (self._root / key).resolve()  # following symlinks: one may point out of the root
        if not path.is_relative_to(workspace_root):
            raise StorageKeyError("the key resolves outside this workspace")
        return path

    def put(self, ctx: RequestContext, key: str, data: bytes) -> None:
        path = self._path(ctx, key)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")  # created 0600
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def get(self, ctx: RequestContext, key: str) -> bytes:
        return self._path(ctx, key).read_bytes()

    def delete(self, ctx: RequestContext, key: str) -> None:
        self._path(ctx, key).unlink(missing_ok=True)


def get_storage() -> StoragePort:
    return LocalFileStorage(settings.COLLECTIQ_STORAGE_DIR)
