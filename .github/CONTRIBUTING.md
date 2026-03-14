# Contributing to obsura-api

Thanks for contributing.

`obsura-api` is a security-first backend for reviewable sanitization workflows.
Changes are evaluated not only on correctness, but also on whether they protect
user privacy, preserve review-first behavior, and avoid accidental data
exposure.

## Before You Start

- Read [README.md](../README.md) for the project layout and local development
  flow.
- Read [SECURITY.md](SECURITY.md) before working on vulnerabilities or sensitive
  behavior.
- Review the product and architecture docs under [`docs/`](../docs/README.md)
  when making workflow or API changes.

## Ways to Contribute

- report bugs
- propose features
- improve docs
- add tests
- submit implementation fixes
- improve security hardening

## Contribution Expectations

### Security and privacy requirements

Every contribution must preserve these rules:

- do not introduce raw sensitive text persistence without explicit maintainer
  approval
- do not log secrets, OCR text, credentials, tokens, or user-submitted payloads
- do not commit real customer data, production screenshots, or live keys
- use sanitized fixtures and examples only
- keep security defaults conservative

### Engineering expectations

- keep changes scoped and reviewable
- add or update tests for behavior changes
- update docs when API contracts, workflows, or operational behavior change
- regenerate `openapi.json` and `postman.json` after route or schema changes
- prefer explicit, maintainable code over clever shortcuts

## Development Setup

1. Create a virtual environment.
2. Install dependencies with `python -m pip install -e .[dev]`.
3. Copy `.env.example` to `.env` if needed.
4. Apply migrations with `obsura-api-migrate upgrade head`.
5. Run the API with `python -m obsura_api.main`.
6. Run tests with `python -m pytest`.

## Pull Request Guidelines

- use a focused branch for each feature or fix
- explain the change, risk, and validation performed
- call out security-sensitive behavior explicitly
- include migration notes when schema or operational behavior changes
- do not combine unrelated refactors with security fixes unless necessary

## Issue Reporting

For public bug reports and feature requests, use GitHub Issues.

Do not post:

- secrets
- live access tokens
- raw customer data
- exploitable vulnerability details
- unsanitized screenshots or logs

Use [SECURITY.md](SECURITY.md) for vulnerability disclosure.
