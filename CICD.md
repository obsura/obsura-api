# Obsura API CI/CD

This document defines the approved CI/CD shape for `obsura-api` at the policy level.

It does not define workflow YAML. It defines the branch model, release behavior, deployment expectations, and security rules that future automation must follow.

## 1. CI/CD Philosophy

The CI/CD model must be:
- simple
- traceable
- container-first
- branch-driven
- practical for a small team or solo maintainer

The goal is predictable delivery, not elaborate release ceremony.

## 2. Branch Model

The approved branch model is:
- `dev`
- `main`

`dev` is the active development and integration branch.

`main` is the stable release branch.

No additional long-lived branches are required by policy at this stage.

## 3. `dev` and `main` Roles

### `dev`

`dev` is used for:
- integrating completed pull requests
- publishing the latest development image
- driving development-environment deployment

### `main`

`main` is used for:
- stable releases
- production image publishing
- GitHub releases
- production deployment

## 4. CI on Pull Requests

All pull requests targeting `dev` or `main` must run CI validation.

At minimum, pull request CI should include:
- linting or formatting checks
- test execution when tests exist
- build validation
- Docker image build validation without publishing

Pull request CI exists to prevent broken changes from entering the integration or release branch.

## 5. Docker Image Publishing on `dev`

A push to `dev` must trigger development publishing behavior.

That behavior must include:
- CI execution
- Docker image build
- image publishing to the container registry
- deployment to the development environment

Approved development tags:
- `dev`
- `dev-<short-sha>`

`dev` is the moving tag for the current development image. `dev-<short-sha>` provides an immutable traceable reference.

## 6. Release Behavior on `main`

A push to `main` must trigger release behavior.

That behavior must include:
- CI execution
- Docker image build
- stable image publishing
- creation or update of release artifacts
- GitHub release creation
- deployment to the production environment

Approved stable tags:
- `latest`
- `<short-sha>`
- a future version tag when formal versioning is introduced

The moving tag supports normal consumption. The immutable tag supports rollback and traceability.

## 7. Image Tag Strategy

The approved image tag strategy is:
- moving tags for the latest deployable branch state
- immutable tags for commit-level traceability

Required branch-based tags:
- `dev`
- `dev-<short-sha>`
- `latest`
- `<short-sha>`

Version tags may be added later, but branch and commit traceability must remain available.

## 8. Development Deployment Policy

Development deployment should happen automatically from `dev`.

The purpose of the development environment is:
- fast iteration
- early integration validation
- quick access to a running build

Development deployment should favor speed and traceability over release ceremony.

## 9. Production Deployment Policy

Production deployment should follow successful pushes to `main`.

Production deployment may be:
- fully automatic
- or protected by an environment approval step

Whichever model is chosen during implementation, production deployment must preserve:
- traceability
- repeatability
- a clear relation between commit, image, release, and deployed version

## 10. Security Rules for CI/CD

The CI/CD system must follow these security rules:
- use the minimum permissions required
- protect registry and deployment secrets
- separate development and production deployment concerns
- avoid unsafe direct publication from untrusted branches
- maintain traceability between source commit and published artifact
- avoid embedding secrets into images or logs

Security should be strong enough for real project use without creating unnecessary delivery friction.

## 11. Branch Protection Expectations

Branch protection should exist for `main` and should preferably also exist for `dev`.

Protection expectations include:
- required status checks before merge
- pull-request-based merge flow for `main`
- restricted direct pushes where practical
- a reviewable path into the stable branch

The repository should prefer safe defaults even if the project is still maintained by a small team.

## 12. What Is Intentionally Deferred

The following CI/CD concerns are intentionally deferred:
- multi-environment orchestration beyond development and production
- advanced rollback automation
- blue-green or canary release strategies
- multi-region deployment
- release-train management
- monorepo-wide orchestration complexity
- enterprise-grade deployment governance

These may be added later if the product grows to require them.

## 13. Approved CI/CD Statement

The approved CI/CD shape for `obsura-api` is:
- CI runs on pull requests to `dev` and `main`
- pushes to `dev` publish development Docker images and deploy to development
- pushes to `main` publish stable Docker images, create a GitHub release, and deploy to production
- Docker images are the primary deployment artifact
- image tagging must include both moving tags and immutable traceable tags
- the overall system must remain simple, secure, and easy to reason about
