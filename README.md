# obsura-api

`obsura-api` is the backend workflow and orchestration layer for Obsura. It is
responsible for review-first sanitization flows, persistent studio assets,
search, and job history across text, CSV, PDF, screenshots, and image-region
workflows.

## Current Scope

This repository currently provides:

- a FastAPI application with clear domain and route boundaries
- persistent studio assets for patterns, custom entities, and reusable
  configurations
- persisted bulk text submissions that group multiple reviewable child jobs
- bulk review and bulk text transform across one persisted bulk run
- built-in, custom, exact-value, and manual text detection
- review-first CSV file workflows with cell-level findings and safe export
- reviewable job history and finding decisions
- text transformation with semantic, custom, partial-mask, and stable-alias
  modes
- review-first PDF text extraction workflows for text-based documents
- image-region transformation for blur, pixelation, masks, and overlays using
  manual or pre-supplied regions
- optional Presidio-backed NLP PII detection layered onto text and OCR flows
- pluggable provider boundaries for OCR and face detection
- optional Tesseract-backed OCR for screenshot text detection and reviewable
  OCR-derived image regions

Automatic OCR and automatic face detection remain provider-based. The default
implementation keeps those boundaries explicit, while the OCR path now supports
an optional Tesseract backend for screenshot-first workflows. Text PII detection
can also be augmented with an optional Presidio backend.

## Standards Alignment

This repository follows the product direction in the repository docs and the
cross-project guidance from `obsura-standards`.

Primary project documents:

- [docs/README.md](docs/README.md)
- [docs/product/REQUIREMENTS.md](docs/product/REQUIREMENTS.md)
- [docs/product/SCENARIOS.md](docs/product/SCENARIOS.md)
- [docs/product/NON_GOALS.md](docs/product/NON_GOALS.md)
- [docs/architecture/STACK.md](docs/architecture/STACK.md)
- [docs/architecture/TOOLING.md](docs/architecture/TOOLING.md)
- [docs/architecture/CODE_STANDARDS.md](docs/architecture/CODE_STANDARDS.md)
- [docs/operations/CICD.md](docs/operations/CICD.md)
- [docs/legal/OPEN_SOURCE_POLICY.md](docs/legal/OPEN_SOURCE_POLICY.md)
- [docs/legal/THIRD_PARTY_NOTICES.md](docs/legal/THIRD_PARTY_NOTICES.md)
- [docs/legal/DEPENDENCY_LICENSE_INVENTORY.md](docs/legal/DEPENDENCY_LICENSE_INVENTORY.md)

The main local deviation is the runtime stack:

- `obsura-standards` is broadly TypeScript-first across the project
- `obsura-api` is intentionally Python/FastAPI-first because the approved local
  stack and tooling documents freeze Python around detection, OCR, and
  image-processing fit

That deviation is explicit rather than accidental.

## Open Source and Community

The repository-level open-source governance files are:

- [LICENSE](LICENSE)
- [.github/CODE_OF_CONDUCT.md](.github/CODE_OF_CONDUCT.md)
- [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md)
- [.github/SECURITY.md](.github/SECURITY.md)
- [.github/SUPPORT.md](.github/SUPPORT.md)
- [.github/GOVERNANCE.md](.github/GOVERNANCE.md)

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
8. Install local hooks with `python -m pre_commit install`.

Quality commands:

- `python -m ruff format src tests`
- `python -m ruff check src tests`
- `python -m mypy`
- `python -m pytest --cov=src/obsura_api`

The default database is SQLite for local execution and tests. Production should
use PostgreSQL as defined in
[docs/architecture/STACK.md](docs/architecture/STACK.md).

Alembic migrations are now the authoritative schema mechanism for the project.
The API no longer treats SQLAlchemy `create_all()` as the production schema
evolution path.

Development/test convenience:

- if `OBSURA_AUTO_CREATE_SCHEMA=true`, the app will automatically run Alembic
  migrations up to the current head on startup
- this is intended only for development and tests
- production must keep `OBSURA_AUTO_CREATE_SCHEMA=false`
- local frontend origins `http://127.0.0.1:3000` and `http://localhost:3000`
  are allowed by default through CORS
- override allowed origins with `OBSURA_CORS_ALLOWED_ORIGINS` using either a
  comma-separated list or a JSON array string
- supported aliases for that setting are `CORS_ALLOWED_ORIGINS`,
  `OBSURA_ALLOWED_HOSTS`, and `ALLOWED_HOSTS`
- because this feeds CORS, values must be full origins such as
  `https://obsura.one`, not bare host names

Current operational endpoints:

- `GET /` and `GET /api` for a friendly service root with docs and OpenAPI links
- `GET /api/v1/health` for liveness
- `GET /api/v1/ready` for dependency-aware readiness
- `GET /api/v1/version` for runtime version and backend metadata
- `POST /api/v1/bulk/text/analyze` for review-first bulk text analysis
- `POST /api/v1/workflows/csv/analyze` and related CSV transform routes
- `POST /api/v1/workflows/documents/analyze` and related PDF transform routes
- `GET /api/v1/bulk/jobs` and `GET /api/v1/bulk/jobs/{bulk_id}` for bulk run
  inspection
- `POST /api/v1/bulk/jobs/{bulk_id}/review` for bulk finding review
- `POST /api/v1/bulk/text/transform` for review-first bulk text output generation

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
3. Set `POSTGRES_PASSWORD` and make sure `DATABASE_URL` uses the same
   credentials and the host name `postgres`.
4. Start the stack with `docker compose up -d`.

The compose stack includes:

- PostgreSQL with a persistent volume
- a one-shot migration service
- the API container with a persistent storage volume
- healthchecks and startup ordering
- a read-only API filesystem with a writable storage volume and `/tmp` tmpfs

The `obsura-init-db` service now runs:

```bash
obsura-api-migrate upgrade head
```

The API container expects the database to already be at the current Alembic
head. In production mode it will fail fast if the schema is missing, unstamped,
or behind.

The compose file now expects a real `.env` file. It uses `.env` in two ways:

- Docker Compose reads values such as `OBSURA_API_IMAGE`,
  `POSTGRES_PASSWORD`, and `DATABASE_URL`
- the containers also load `.env` directly through `env_file`

By default the API binds only to `127.0.0.1:8000`. After startup, access:

- `http://localhost:8000/api/v1/health`
- `http://localhost:8000/api/v1/ready`
- `http://localhost:8000/api/v1/version`
- `http://localhost:8000/docs`

Operational commands:

- `docker compose up -d`
- `docker compose logs -f obsura-api`
- `docker compose logs -f obsura-init-db`
- `docker compose ps`

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

For frontend integration guidance, use:

- [guide/FRONTEND_API_GUIDE.md](guide/FRONTEND_API_GUIDE.md)

Regenerate them after route or schema changes with either:

- `python -m obsura_api.tools.api_artifacts`
- `obsura-api-artifacts`

The Postman collection is designed to be chained:

- create requests automatically capture IDs such as `patternId`, `entityId`,
  `configurationId`, `jobId`, and `findingId`
- subsequent requests use those collection variables in URLs and example bodies
- bulk requests also capture `bulkId` so the analyze, review, and transform flow
  can be exercised without manual ID copying
- image transform responses also capture `outputFilePath` and `outputMediaUrl`

## Validation and Limits

The API now enforces a few runtime safety defaults that are relevant for real
deployments:

- `OBSURA_MAX_UPLOAD_BYTES` limits multipart file uploads
- `OBSURA_MAX_IMAGE_PIXELS` limits image dimensions by total pixel count
- `OBSURA_MAX_BULK_TEXT_ITEMS` limits items per bulk text request
- `OBSURA_MAX_BULK_TEXT_ITEM_CHARACTERS` limits characters per bulk text item
- `OBSURA_MAX_BULK_TEXT_TOTAL_CHARACTERS` limits the combined payload size for
  bulk text analysis
- `OBSURA_MAX_CSV_ROWS` limits CSV row count
- `OBSURA_MAX_CSV_COLUMNS` limits CSV column count
- `OBSURA_MAX_CSV_CHARACTERS` limits CSV total character count
- `OBSURA_MAX_DOCUMENT_PAGES` limits PDF page count
- `OBSURA_MAX_DOCUMENT_EXTRACTED_CHARACTERS` limits extracted PDF text
- image uploads must use a supported image MIME type
- public API responses expose storage-root relative file references rather than
  raw absolute filesystem paths

Image review jobs retain source files by default so reviewed job exports can be
re-run safely. Clients may explicitly disable that on image analysis requests by
setting `persist_source_content` to `false`.

## Bulk Text Flow

The current bulk implementation is text-only and review-first.

Recommended order:

1. `POST /api/v1/bulk/text/analyze`
2. `GET /api/v1/jobs/{job_id}` for any child jobs whose findings you want to inspect
3. `POST /api/v1/bulk/jobs/{bulk_id}/review`
4. `POST /api/v1/bulk/text/transform`

Contract notes:

- bulk runs are persistent parent resources; valid items create persistent child
  jobs
- bulk run `success_count` and `failure_count` describe analyze-time submission
  validity, not review/transform action counts
- bulk review and bulk transform responses return their own per-action
  `success_count`, `failure_count`, and `skipped_count`
- finding summaries use the standard `total`, `pending`, `approved`, and
  `rejected` shape across single-job and bulk responses
- stored file paths in API responses are storage-relative references, not host
  filesystem paths

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
