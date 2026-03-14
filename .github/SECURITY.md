# Security Policy

`obsura-api` is a security-first project. Protecting user data, preventing
sensitive persistence, and avoiding disclosure through logs or artifacts take
priority over convenience.

## Supported Versions

Security fixes are handled on the actively maintained branches below.

| Version / branch | Supported |
| --- | --- |
| `main` latest release | Yes |
| `dev` | Yes |
| feature branches | No |
| unmaintained historical branches | No |

For pre-release periods before a formal stable release, report against the
current `dev` branch behavior unless maintainers instruct otherwise.

## Reporting a Vulnerability

Preferred channel:

- use GitHub Private Vulnerability Reporting or a private GitHub security
  advisory for this repository, if enabled

If a private GitHub security channel is unavailable:

- contact the project maintainers privately through the repository owner's
  security contact

Do not report vulnerabilities through:

- public GitHub issues
- pull requests
- public discussions
- chat messages containing live secrets or PII

If you cannot find a private reporting channel, open a minimal public issue
requesting a private contact path without disclosing the vulnerability details.

## What to Include

- affected version, branch, or deployment context
- clear reproduction steps
- expected impact
- whether sensitive data exposure is involved
- whether the issue is actively exploitable
- sanitized logs or sample payloads only

Do not include:

- production secrets
- live credentials
- customer PII
- raw customer documents or screenshots

## Response Targets

The project aims to:

- acknowledge new reports within 5 business days
- provide an initial triage response within 10 business days when feasible
- coordinate remediation and disclosure timing with the reporter for confirmed
  issues

These are targets, not guarantees.

## Disclosure Expectations

- give maintainers reasonable time to investigate and patch
- avoid public disclosure before a fix or mitigation is available
- keep proof-of-concept data sanitized unless maintainers explicitly request a
  private reproduction artifact

## Security Design Priorities

When evaluating fixes, maintainers will prioritize:

- preventing raw sensitive persistence
- preventing sensitive logging
- reducing unsafe defaults
- protecting review integrity and transform correctness
- minimizing exploit surface in uploaded files and parser paths
