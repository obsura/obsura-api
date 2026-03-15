# Obsura API Stack

This document defines the approved stack direction for `obsura-api`.

It is intentionally practical and frozen enough for execution. The goal is to choose a stack that supports the product model without introducing unnecessary system complexity.

## 1. Stack Philosophy

The approved stack must be:
- backend-first
- simple before scalable
- compatible with the required sanitization tooling
- easy to run locally
- easy to self-host
- easy for contributors to understand
- strong enough for text, screenshot, and image workflows

The stack should stay minimal until the core product workflows are proven.

## 2. API Framework Direction

The approved API framework direction is **FastAPI**.

FastAPI is the approved starting point because the API needs:
- structured request validation
- explicit models for findings, jobs, and saved assets
- orchestration-friendly endpoints
- practical local development
- straightforward container deployment

## 3. Language Direction

The approved backend language direction is **Python**.

Python is the approved language because the product depends on:
- text-detection tooling
- OCR orchestration
- image-processing workflows
- face-detection workflows
- future document-processing pipelines

Python also keeps the stack aligned with the open-source tooling most relevant to Obsura.

## 4. Database Direction

The approved database direction is **PostgreSQL**.

SQLite is still allowed as a local-only development and test convenience, but
it is not the approved production database.

`obsura-api` is not a stateless utility. It must support a persistent studio model that stores:
- patterns
- custom entities
- packs, profiles, and presets
- categories and tags
- jobs and run history
- review decisions
- user preferences
- future project or workspace organization

A relational database is the approved baseline for this model.

## 5. Storage Direction

The approved initial storage direction for files and generated artifacts is **local filesystem storage**.

This storage is expected to handle:
- uploaded source files
- generated outputs
- temporary processing artifacts where needed

This keeps the first system easy to run and self-host. Object storage may be added later, but it is not required for the initial execution phase.

## 6. Deployment Direction

The approved initial deployment direction is **containerized deployment with Docker Compose**.

This direction is approved because it is:
- reproducible
- self-hostable
- easy to run locally
- simple enough for early product execution

The initial deployment model should remain compact rather than splitting the system into many services too early.

## 7. Why Server-Side Is Required

Obsura requires a server-side core because the product must support:
- persistent studio assets
- job and run history
- OCR workflows
- image processing
- face detection
- reusable transformation pipelines
- future document-processing workflows
- consistent policy and review data across clients

The product is not only a temporary browser utility. It needs a durable backend source of truth.

## 8. Why Not Client-Side Only

Client-side-only architecture is not the approved direction.

A client-side-only system would be a poor fit for the current product definition because Obsura depends on:
- server-managed persistence
- reusable saved assets
- searchable studio data
- heavier processing pipelines
- consistent workflow orchestration
- self-hosted operation that does not depend on browser capabilities alone

Clients may remain lightweight, but the workflow core belongs on the server.

## 9. Why the Stack Is Minimal by Design

The approved initial stack is intentionally lean.

Required initial core:
- Python
- FastAPI
- PostgreSQL
- local filesystem storage
- Docker Compose

Not required initially:
- microservice sprawl
- message queues
- event buses
- distributed object storage
- multiple databases
- orchestration platforms
- service meshes

The product risk is workflow correctness and usefulness, not infrastructure sophistication.

## 10. Future Expansion Boundaries

The stack must be able to grow later, but future needs must not dictate the first implementation.

Possible future additions include:
- object storage
- background job workers
- caching layers
- queue systems
- dedicated document-processing workers
- more advanced deployment environments

These are future options, not current obligations.

## 11. Approved Stack Statement

The current approved stack direction for `obsura-api` is:
- **Python** for backend logic
- **FastAPI** for the API layer
- **PostgreSQL** for persistent studio and workflow data
- **local filesystem storage** for initial file and output handling
- **Docker Compose** for local and early hosted deployment

This stack is approved because it is practical, self-hosted friendly, and aligned with the product requirement that Obsura be a persistent workflow core rather than a one-shot utility.
