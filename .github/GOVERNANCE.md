# Governance

## Model

`obsura-api` uses a maintainer-led governance model.

There is no formal foundation or elected committee for this repository at the
current stage. Maintainers are responsible for roadmap direction, release
approval, and final technical decisions.

## Roles

### Maintainers

Maintainers are responsible for:

- reviewing and merging changes
- protecting the security posture of the project
- deciding release timing and backports
- approving dependency and license changes
- curating project policies and documentation

### Contributors

Contributors may:

- propose changes through issues and pull requests
- improve code, tests, docs, and legal notices
- suggest roadmap direction

Contributors do not automatically gain merge or release authority.

## Decision Principles

Maintainers will prioritize:

- security before convenience
- privacy before feature breadth
- explicit reviewable workflows before blind automation
- self-hostable and understandable infrastructure
- compatibility with the repository license and legal obligations

## Branch and Release Shape

- `dev` is the integration branch
- `main` is the stable release branch
- short-lived feature branches are preferred for individual changes

## Changes Requiring Explicit Maintainer Approval

- security posture changes
- persistence or logging behavior changes
- breaking API changes
- new external service dependencies
- new dependency licenses or materially changed license obligations
- changes to governance, conduct, support, or security policies
