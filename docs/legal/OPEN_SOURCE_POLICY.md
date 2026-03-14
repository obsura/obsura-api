# Open Source Policy

## Purpose

This document describes how `obsura-api` manages open-source licensing,
third-party components, and repository-level project policies.

It is an operational project policy, not legal advice.

## First-Party Licensing

`obsura-api` is licensed under `AGPL-3.0-or-later`.

The authoritative project license file is the repository root
[LICENSE](../../LICENSE).

## Community Health Files

The repository-level community and policy files live under `.github/`:

- [`CODE_OF_CONDUCT.md`](../../.github/CODE_OF_CONDUCT.md)
- [`CONTRIBUTING.md`](../../.github/CONTRIBUTING.md)
- [`SECURITY.md`](../../.github/SECURITY.md)
- [`SUPPORT.md`](../../.github/SUPPORT.md)
- [`GOVERNANCE.md`](../../.github/GOVERNANCE.md)

## Third-Party Component Intake

New third-party dependencies must be reviewed before merge.

At minimum, the review should cover:

- security implications
- operational impact
- maintenance maturity
- deployment model
- license and notice obligations
- compatibility with the project's security-first architecture

Dependencies that materially increase data exposure risk, add unnecessary
network trust, or introduce unclear legal terms should not be added casually.

## License Review Expectations

The project prefers dependencies with well-understood open-source licenses and
clear redistribution terms.

Any dependency that introduces new reciprocal, source-available, proprietary,
or service-restriction obligations requires explicit maintainer review before
merge.

## Inventory and Notice Maintenance

The repository keeps:

- [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for human-readable notice
  coverage
- [`DEPENDENCY_LICENSE_INVENTORY.md`](DEPENDENCY_LICENSE_INVENTORY.md) for the
  versioned dependency inventory reviewed in the repository context

When direct dependencies, runtime images, or packaged system components change,
the legal docs should be reviewed and updated in the same change where
practical.

## Security-First Constraints

Because `obsura-api` processes sensitive content, dependency decisions must also
consider:

- parser attack surface
- file-handling risk
- OCR and image-processing exposure
- default logging behavior
- data persistence behavior
- outbound network expectations

## Release Expectations

Before a formal release, maintainers should confirm:

- the project license metadata matches the distributed artifacts
- third-party notices still reflect the shipped runtime
- the dependency inventory has been reviewed in the release environment
- no new dependency or build-step has introduced undeclared obligations
