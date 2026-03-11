# obsura-api

`obsura-api` is the backend workflow and orchestration layer for Obsura. It is
responsible for review-first sanitization flows, persistent studio assets,
search, and job history across text, screenshots, and image-region workflows.

## Current Scope

This repository currently provides:

- a FastAPI application with clear domain and route boundaries
- persistent studio assets for patterns, custom entities, and reusable
  configurations
- built-in, custom, exact-value, and manual text detection
- reviewable job history and finding decisions
- text transformation with semantic, custom, partial-mask, and stable-alias
  modes
- image-region transformation for blur, pixelation, masks, and overlays using
  manual or pre-supplied regions
- pluggable provider boundaries for OCR and face detection
- optional Tesseract-backed OCR for screenshot text detection and reviewable
  OCR-derived image regions

Automatic OCR and automatic face detection remain provider-based. The default
implementation keeps those boundaries explicit, while the OCR path now supports
an optional Tesseract backend for screenshot-first workflows.

## Standards Alignment

This repository follows the product direction in the local root Markdown files
and the cross-project guidance from `obsura-standards`.

The main local deviation is the runtime stack:

- `obsura-standards` is broadly TypeScript-first across the project
- `obsura-api` is intentionally Python/FastAPI-first because the approved local
  stack and tooling documents freeze Python around detection, OCR, and
  image-processing fit

That deviation is explicit rather than accidental.

## Project Layout

```text
src/obsura_api/
  api/        FastAPI routers and dependencies
  core/       settings and application wiring
  db/         SQLAlchemy models and session helpers
  domain/     shared enums and request/response schemas
  services/   detection, transformation, storage, search, and job logic
tests/        behavior-focused API and service tests
```

## Local Development

1. Create a virtual environment.
2. Install dependencies with `python -m pip install -e .[dev]`.
3. Copy `.env.example` to `.env` if you want to customize settings.
4. Apply migrations with `obsura-api-migrate upgrade head`.
5. Run the API with `python -m obsura_api.main`.
6. Run tests with `python -m pytest`.
7. Regenerate API artifacts with `python -m obsura_api.tools.api_artifacts`.

The default database is SQLite for local execution and tests. Production should
use PostgreSQL as defined in [STACK.md](STACK.md).

Alembic migrations are now the authoritative schema mechanism for the project.
The API no longer treats SQLAlchemy `create_all()` as the production schema
evolution path.

Development/test convenience:

- if `OBSURA_AUTO_CREATE_SCHEMA=true`, the app will automatically run Alembic
  migrations up to the current head on startup
- this is intended only for development and tests
- production must keep `OBSURA_AUTO_CREATE_SCHEMA=false`

Current operational endpoints:

- `GET /api/v1/health` for liveness
- `GET /api/v1/ready` for dependency-aware readiness
- `GET /api/v1/version` for runtime version and backend metadata

## Docker

Build the production image locally with:

```bash
docker build -t obsura-api:dev .
```

Run it locally with:

```bash
docker run --rm -p 8000:8000 obsura-api:dev
```

The root [Dockerfile](Dockerfile) is multi-stage, runs as a non-root user, and
is the image used by the `dev` branch CI workflow.

For a containerized local or self-hosted deployment, use
[docker-compose.yaml](docker-compose.yaml).

Typical flow:

1. Copy `.env.example` to `.env`.
2. Set `OBSURA_API_IMAGE` to the image tag you want to run.
3. Set `POSTGRES_PASSWORD` and `DATABASE_URL`.
4. Start the stack with `docker compose up -d`.

The compose stack includes:

- PostgreSQL with a persistent named volume
- a one-shot migration service
- the API container with a persistent storage volume
- healthchecks and startup ordering

The `obsura-init-db` service now runs:

```bash
obsura-api-migrate upgrade head
```

The API container expects the database to already be at the current Alembic
head. In production mode it will fail fast if the schema is missing, unstamped,
or behind.

By default the API binds only to `127.0.0.1:8000`. After startup, access:

- `http://localhost:8000/api/v1/health`
- `http://localhost:8000/api/v1/ready`
- `http://localhost:8000/api/v1/version`
- `http://localhost:8000/docs`

## CI/CD

The repository includes a development workflow at
[dev.yml](.github/workflows/dev.yml).

Behavior:

- pull requests targeting `dev` run tests and validate the Docker build
- pushes to `dev` publish `dev` and `dev-<short-sha>` tags to GitHub Container
  Registry

## API Artifacts

The repository keeps two generated API client artifacts at the root:

- `openapi.json`
- `postman.json`

Regenerate them after route or schema changes with either:

- `python -m obsura_api.tools.api_artifacts`
- `obsura-api-artifacts`

The Postman collection is designed to be chained:

- create requests automatically capture IDs such as `patternId`, `entityId`,
  `configurationId`, `jobId`, and `findingId`
- subsequent requests use those collection variables in URLs and example bodies
- image transform responses also capture `outputFilePath` and `outputMediaUrl`

## Validation and Limits

The API now enforces a few runtime safety defaults that are relevant for real
deployments:

- `OBSURA_MAX_UPLOAD_BYTES` limits multipart file uploads
- `OBSURA_MAX_IMAGE_PIXELS` limits image dimensions by total pixel count
- image uploads must use a supported image MIME type
- public API responses expose storage-root relative file references rather than
  raw absolute filesystem paths

Image review jobs retain source files by default so reviewed job exports can be
re-run safely. Clients may explicitly disable that on image analysis requests by
setting `persist_source_content` to `false`.

## Database Migrations

Local operator commands:

```bash
obsura-api-migrate upgrade head
obsura-api-migrate current
obsura-api-migrate check
```

Contributor workflow:

```bash
alembic -c alembic.ini revision --autogenerate -m "describe_change"
alembic -c alembic.ini upgrade head
```

Production expectations:

- set `DATABASE_URL` to PostgreSQL
- run migrations explicitly before or during deploy
- keep `OBSURA_AUTO_CREATE_SCHEMA=false`
- if the database is missing a revision or behind the current head, API startup
  and `/api/v1/ready` will fail clearly

Compatibility note:

- the initial baseline migration is idempotent on upgrade
- that allows older bootstrap-created databases without an `alembic_version`
  row to be reconciled by running `upgrade head`
