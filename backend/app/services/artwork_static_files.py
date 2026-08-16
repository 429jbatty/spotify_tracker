import re

from fastapi.staticfiles import StaticFiles
from starlette.responses import Response


CONTENT_HASH_PATTERN = re.compile(
    r"-sha256-[0-9a-f]{12}(?:-\d+)?\.[A-Za-z0-9]+$"
)
IMMUTABLE_CACHE_CONTROL = "public, max-age=31536000, immutable"
LEGACY_CACHE_CONTROL = "public, max-age=3600"


class ArtworkStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        cache_control = (
            IMMUTABLE_CACHE_CONTROL
            if CONTENT_HASH_PATTERN.search(path)
            else LEGACY_CACHE_CONTROL
        )
        response.headers["Cache-Control"] = cache_control
        return response
