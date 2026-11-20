"""Localized automatic-sync validation errors, shared by worker and review."""
from .messages import KuulasError


class SyncError(KuulasError, ValueError):
    pass


def fail(reason):
    key = "error.sync." + reason
    raise SyncError(key)
