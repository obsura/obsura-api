# Third-Party Notices

`obsura-api` is distributed under `AGPL-3.0-or-later` and depends on third-party
open-source software for API serving, validation, persistence, OCR, and image
processing.

This file is a practical notice file for the repository. It is not a substitute
for the full license texts provided by upstream projects or package managers.

## Scope

These notices currently cover:

- declared Python dependencies in `pyproject.toml`
- runtime system packages referenced by the root `Dockerfile`
- the PostgreSQL container image referenced by `docker-compose.yaml`

## Key Third-Party Components

- FastAPI for the HTTP API layer
- SQLAlchemy for ORM and database access
- Pillow for image processing
- python-multipart for multipart upload parsing
- pydantic-settings for environment-driven configuration
- Uvicorn for ASGI serving
- Tesseract OCR binaries in the production container image
- PostgreSQL in the Compose deployment example

## Distribution Notes

- Third-party components remain subject to their own license terms.
- Self-hosted deployers are responsible for reviewing the licenses of the exact
  dependency set and container image contents they ship.
- Before a formal release, the dependency inventory should be regenerated in the
  release environment so versions and license expressions match the exact built
  artifact.

## Source of Inventory Data

The accompanying `DEPENDENCY_LICENSE_INVENTORY.md` was prepared from:

- the repository `pyproject.toml`
- local package metadata available during this stabilization sprint
- the repository `Dockerfile`
- the repository `docker-compose.yaml`

Dependencies that were declared but not installed in the local review
environment are marked clearly in the inventory rather than guessed.
