"""Entrypoint for local Obsura API execution."""

from __future__ import annotations

import uvicorn


def main() -> None:
    """Run the API with a local development server."""

    uvicorn.run(
        "obsura_api.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        reload=False,
        access_log=False,
    )


if __name__ == "__main__":
    main()
