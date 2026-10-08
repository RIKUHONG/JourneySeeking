"""Errors raised by the trip storage boundary."""


class TripStorageError(Exception):
    """Base class for storage failures."""


class TripNotFoundError(TripStorageError):
    """The requested trip or version does not exist."""


class TripVersionConflictError(TripStorageError):
    """The expected version is no longer current."""
