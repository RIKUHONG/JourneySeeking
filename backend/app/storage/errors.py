"""Errors raised by the trip storage boundary."""


class TripStorageError(Exception):
    """Base class for storage failures."""


class TripNotFoundError(TripStorageError):
    """The requested trip or version does not exist."""


class TripVersionConflictError(TripStorageError):
    """The expected version is no longer current."""


class InvalidTripCursorError(TripStorageError):
    """The opaque list cursor cannot be decoded or has the wrong shape."""
