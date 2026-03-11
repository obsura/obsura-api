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

Automatic OCR and automatic face detection are intentionally provider-based.
The default implementation keeps those boundaries explicit without pretending
that a no-op fallback is a finished detection system.

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
4. Run the API with `python -m obsura_api.main`.
5. Run tests with `python -m pytest`.
6. Regenerate API artifacts with `python -m obsura_api.tools.api_artifacts`.

The default database is SQLite for local execution and tests. Production should
use PostgreSQL as defined in [STACK.md](STACK.md).

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
- a one-shot schema initialization service
- the API container with a persistent storage volume
- healthchecks and startup ordering

Until Alembic migrations are added, the API container also defaults
`OBSURA_AUTO_CREATE_SCHEMA=true` in the compose stack. That makes startup
self-heal when the schema is missing and prevents the service from coming up
healthy while `/api/v1/studio` fails due to absent tables.

By default the API binds only to `127.0.0.1:8000`. After startup, access:

- `http://localhost:8000/api/v1/health`
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
