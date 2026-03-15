# Third-Party Notices

`obsura-api` is distributed under `AGPL-3.0-or-later` and integrates third-party
open-source software for API serving, validation, persistence, OCR, document
handling, and image-processing workflows.

This file is a repository-level notice summary. It is not a substitute for the
full license texts and copyright notices provided by upstream projects.

## Scope

These notices cover the main third-party software families used by the current
API implementation and deployment examples:

- declared Python dependencies in `pyproject.toml`
- optional Python feature dependencies enabled by the current Docker build
- runtime system packages installed by the repository `Dockerfile`
- the PostgreSQL image referenced by `docker-compose.yaml`

## Core Application Components

| Component | How `obsura-api` uses it |
| --- | --- |
| Alembic | database schema migration management |
| FastAPI | HTTP API framework and OpenAPI generation |
| SQLAlchemy | ORM and persistence layer |
| Pydantic Settings | environment-driven configuration loading |
| python-multipart | multipart form parsing for uploads |
| Uvicorn | ASGI application serving |
| Psycopg | PostgreSQL database connectivity |

## Content and Workflow Components

| Component | How `obsura-api` uses it |
| --- | --- |
| Pillow | image decoding, transformation, re-encoding, and safe rendering |
| OpenCV-Python | optional computer-vision and region-processing support |
| PyTesseract | Python bridge for OCR integration |
| Tesseract OCR | OCR engine installed in the runtime image |
| PyPDF | text extraction from text-based PDF documents |
| Microsoft Presidio Analyzer | optional PII detection support |
| Microsoft Presidio Anonymizer | optional text anonymization operator support |

## Build and Platform Components

| Component | How `obsura-api` uses it |
| --- | --- |
| `python:3.13-slim` | builder and runtime container base image |
| `tesseract-ocr-eng` | English OCR language data in the runtime image |
| `postgres:17-alpine` | example Compose database image |
| `en_core_web_sm` | spaCy English model downloaded in the Docker builder flow for Presidio-backed NLP support |
| `es_core_news_sm` | spaCy Spanish model downloaded in the Docker builder flow for Presidio-backed NLP support |

## Distribution Notes

- Third-party components remain subject to their own license terms.
- The authoritative project license is the root [`LICENSE`](../../LICENSE).
- The versioned dependency inventory for the repository is maintained in
  [`DEPENDENCY_LICENSE_INVENTORY.md`](DEPENDENCY_LICENSE_INVENTORY.md).
- The exact dependency tree of a release artifact may include transitive Python
  packages and system packages beyond the top-level components listed here.
- Release packaging should review the shipped image contents in the exact build
  environment before formal distribution.

## Source of Inventory Data

The accompanying inventory was prepared from:

- the repository `pyproject.toml`
- the repository `Dockerfile`
- the repository `docker-compose.yaml`
- locally available package metadata where present

Components that were declared but not installed in the local review environment
are marked clearly in the inventory rather than guessed.
