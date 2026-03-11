# Dependency License Inventory

This inventory is intentionally practical and conservative. It lists the
declared first-party runtime and development dependencies for `obsura-api`,
along with the license information that was available in the local review
environment during the stabilization sprint.

Status meanings:

- `Verified from local package metadata`: confirmed from installed package metadata
- `Declared, not locally verified`: declared in the repository but not installed
  in the local review environment at the time of this inventory

## Python Dependencies

| Package | Role | Version seen locally | License | Status |
| --- | --- | --- | --- | --- |
| fastapi | API framework | 0.135.1 | MIT | Verified from local package metadata |
| opencv-python-headless | Optional face-detection backend dependency | Not installed locally | Not locally verified | Declared, not locally verified |
| pillow | Image processing | 12.1.1 | MIT-CMU | Verified from local package metadata |
| psycopg[binary] | PostgreSQL driver | Not installed locally | Not locally verified | Declared, not locally verified |
| pytesseract | Optional OCR backend integration | Not installed locally | Not locally verified | Declared, not locally verified |
| pydantic-settings | Settings/configuration loading | 2.13.1 | MIT | Verified from local package metadata |
| python-multipart | Multipart form parsing | 0.0.22 | Apache-2.0 | Verified from local package metadata |
| sqlalchemy | ORM and database access | 2.0.48 | MIT | Verified from local package metadata |
| uvicorn | ASGI server | 0.41.0 | BSD-3-Clause | Verified from local package metadata |
| httpx | Development/test HTTP client | 0.28.1 | BSD-3-Clause | Verified from local package metadata |
| pytest | Test runner | 9.0.2 | MIT | Verified from local package metadata |

## Container and Runtime Components

| Component | Source | Notes |
| --- | --- | --- |
| python:3.13-slim | Root `Dockerfile` base image | Upstream image license obligations should be reviewed at release time |
| tesseract-ocr | Installed in runtime image | Included to support the optional Tesseract OCR backend |
| tesseract-ocr-eng | Installed in runtime image | English language data package for Tesseract |
| postgres:17-alpine | `docker-compose.yaml` example service | Separate upstream image and PostgreSQL licensing apply |

## Notes

- This file does not yet include a fully expanded transitive dependency tree.
- Release packaging should regenerate this inventory in the exact build
  environment used for the shipped image.
- Dependencies marked `Declared, not locally verified` should have their SPDX
  identifiers confirmed as part of the release pipeline before distribution.
