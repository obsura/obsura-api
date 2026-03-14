# Code Standards

This document defines the enforced code-quality baseline for `obsura-api`.

The goal is not theoretical purity. The goal is a codebase that is safe,
predictable, easy to review, and easy for new contributors to work on.

## Principles

- security-first defaults are more important than convenience shortcuts
- route-layer HTTP concerns should stay separate from domain and service logic
- typed contracts are preferred over implicit dictionaries where practical
- tests, linting, and type checks must be cheap enough to run frequently
- formatting and import ordering should be automated, not debated in reviews

## Enforced Tooling

The repository currently enforces:

- `ruff format` for consistent formatting
- `ruff check` for import sorting and core correctness linting
- `mypy` on the `api`, `core`, and `domain` packages
- `pytest` with coverage reporting and an `80%` repository coverage floor
- `pre-commit` hooks for local contributor hygiene

## Current Mypy Scope

The typed enforcement scope is intentionally staged.

Current enforced packages:

- `src/obsura_api/api`
- `src/obsura_api/core`
- `src/obsura_api/domain`

The larger service modules are not yet part of the enforced mypy gate because
they still need structural cleanup. Expanding mypy coverage there is planned
work, not forgotten work.

## Contributor Workflow

After installing development dependencies, run:

```bash
python -m ruff format src tests
python -m ruff check src tests
python -m mypy
python -m pytest --cov=src/obsura_api
```

To install local Git hooks:

```bash
python -m pre_commit install
```

## Code Review Expectations

Pull requests should:

- keep feature scope narrow
- include tests for behavior changes
- avoid mixing refactors with unrelated logic changes
- call out security-sensitive changes explicitly
- update `openapi.json` and `postman.json` when the API contract changes

## Architectural Expectations

- API routes should translate HTTP inputs and outputs, not hold business logic
- services should prefer domain/application errors over `HTTPException`
- domain models should stay explicit and typed
- optional provider integrations should fail clearly and safely
- sensitive data must not leak through logs, persistence, or debugging helpers
