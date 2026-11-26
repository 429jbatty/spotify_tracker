"""Register and expose all SQLAlchemy models."""

from .albums import Album, AlbumCreditFact, AlbumMetadataCache
from .authentication import (
    Account,
    AccountSession,
    GoogleOAuthState,
    ProfileOwnershipAssignment,
    SpotifyOAuthState,
)
from .base import Base
from .imports import ImportedListeningEvent, ImportSession, ImportSessionLog
from .spotify import SpotifyStreamingEvent, UserSpotifyCredentials
from .users import AlbumInProgress, AlbumListen, User, UserAlbum, UserAppState

__all__ = [
    "Account",
    "AccountSession",
    "Album",
    "AlbumCreditFact",
    "AlbumInProgress",
    "AlbumListen",
    "AlbumMetadataCache",
    "Base",
    "GoogleOAuthState",
    "ImportSession",
    "ImportSessionLog",
    "ImportedListeningEvent",
    "ProfileOwnershipAssignment",
    "SpotifyOAuthState",
    "SpotifyStreamingEvent",
    "User",
    "UserAlbum",
    "UserAppState",
    "UserSpotifyCredentials",
]
