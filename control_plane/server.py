"""Compatibility marker for the retired stdlib prototype.

The production entrypoint is ``control_plane/backend/app/main.py`` and is
started by Docker Compose. Keeping this marker prevents operators from
accidentally starting the old SQLite/stdlib control plane.
"""

raise SystemExit(
    "The stdlib prototype is retired; run `docker compose -f control_plane/docker-compose.yml up -d --build`."
)
