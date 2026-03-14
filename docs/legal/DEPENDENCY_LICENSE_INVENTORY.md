# Dependency License Inventory

This inventory is intentionally practical and conservative. It records the
top-level dependencies and runtime components used by `obsura-api`, along with
the license information that was available in the local review environment.

Status meanings:

- `Verified from local package metadata`: confirmed from installed package metadata
- `Declared, not locally verified`: declared by the repository but not installed
  in the local review environment at the time of review
- `Image/runtime component`: supplied by the Docker image or deployment example
  rather than local Python package metadata

## Direct Runtime Dependencies

| Package | Role | Declared constraint | Version seen locally | License | Status |
| --- | --- | --- | --- | --- | --- |
| alembic | Database migration management | `>=1.14.0` | 1.18.4 | Not locally normalized | Verified from local package metadata |
| fastapi | API framework | `>=0.116.1` | 0.135.1 | Not locally normalized | Verified from local package metadata |
| opencv-python-headless | Optional image and vision operations | `>=4.9.0` | Not installed locally | Not locally verified | Declared, not locally verified |
| pillow | Image processing | `>=11.2.1` | 12.1.1 | MIT-CMU | Verified from local package metadata |
| pypdf | PDF text extraction | `>=5.4.0` | 6.8.0 | Not locally normalized | Verified from local package metadata |
| psycopg[binary] | PostgreSQL driver | `>=3.2.9` | Not installed locally | Not locally verified | Declared, not locally verified |
| pytesseract | OCR integration bridge | `>=0.3.13` | Not installed locally | Not locally verified | Declared, not locally verified |
| pydantic-settings | Settings/configuration loading | `>=2.8.1` | 2.13.1 | Not locally normalized | Verified from local package metadata |
| python-multipart | Multipart form parsing | `>=0.0.20` | 0.0.22 | Apache-2.0 | Verified from local package metadata |
| sqlalchemy | ORM and database access | `>=2.0.39` | 2.0.48 | MIT | Verified from local package metadata |
| uvicorn | ASGI server | `>=0.34.0` | 0.41.0 | BSD-3-Clause | Verified from local package metadata |

## Optional Feature Dependencies

| Package | Role | Declared constraint | Version seen locally | License | Status |
| --- | --- | --- | --- | --- | --- |
| presidio-analyzer | Optional PII detection backend | `>=2.2.360` | Not installed locally | Not locally verified | Declared, not locally verified |
| presidio-anonymizer | Optional text anonymization backend | `>=2.2.360` | Not installed locally | Not locally verified | Declared, not locally verified |

## Development and Test Dependencies

| Package | Role | Declared constraint | Version seen locally | License | Status |
| --- | --- | --- | --- | --- | --- |
| httpx | Test HTTP client | `>=0.28.1` | 0.28.1 | BSD-3-Clause | Verified from local package metadata |
| pytest | Test runner | `>=8.3.5` | 8.4.2 | MIT | Verified from local package metadata |

## Runtime Image and Deployment Components

| Component | Source | Notes | Status |
| --- | --- | --- | --- |
| `python:3.13-slim` | Root `Dockerfile` builder and runtime base image | Upstream image obligations should be reviewed at release time | Image/runtime component |
| `tesseract-ocr` | Installed in the runtime image | Required for the current OCR-enabled container flow | Image/runtime component |
| `tesseract-ocr-eng` | Installed in the runtime image | English OCR language package for Tesseract | Image/runtime component |
| `postgres:17-alpine` | `docker-compose.yaml` example service | Separate upstream PostgreSQL and image licensing apply | Image/runtime component |
| `en_core_web_sm` | Downloaded in the Docker builder flow | spaCy English model used for the Presidio-enabled image build | Image/runtime component |

## Notes

- This file does not yet include a fully expanded transitive dependency tree.
- The Docker image currently installs the `presidio` extra during build, so
  transitive runtime dependencies such as spaCy are part of the shipped image
  even when they are not listed as top-level direct dependencies in
  `pyproject.toml`.
- Release packaging should regenerate or re-verify this inventory in the exact
  build environment used for the shipped image.
- Entries marked `Not locally normalized` indicate that package metadata was
  present locally, but the SPDX expression should still be confirmed in the
  release pipeline if the project will distribute packaged artifacts publicly.
