# Frontend API Guide

This guide is for `obsura-web` and any frontend team consuming `obsura-api`.

It summarizes the current stable API contract, how to model the client, and
how to build the main review-first product flows without guessing.

## 1. Base Contract

Base URL examples:

- local: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI: `http://127.0.0.1:8000/openapi.json`

Current health and runtime endpoints:

- `GET /api/v1/health`
- `GET /api/v1/ready`
- `GET /api/v1/version`

Frontend expectation:

- use `/api/v1/ready` before treating the backend as fully available
- use `/api/v1/version` for diagnostics, environment display, and operator UI
- do not use `/api/v1/health` as a full readiness signal
- local development CORS allows `http://127.0.0.1:3000` and
  `http://localhost:3000` by default

## 2. Unified Response Shape

Every successful or failed API response uses the same envelope.

Success shape:

```json
{
  "success": true,
  "data": {},
  "pagination": null,
  "message": null,
  "error": null
}
```

Failure shape:

```json
{
  "success": false,
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "details": []
  }
}
```

Frontend rules:

- always check `success`
- read useful payloads from `data`
- read operator-facing failures from `error.message`
- use `error.details` for field errors and advanced UI hints
- do not assume non-`200` responses are the only failure path; still parse JSON

## 3. Pagination Contract

Paged endpoints use query params:

- `page`
- `page_size`

Paged responses include:

```json
{
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_items": 42,
    "total_pages": 3,
    "has_next": true,
    "has_previous": false
  }
}
```

Frontend rules:

- default to `page=1&page_size=20`
- treat `has_next` and `has_previous` as authoritative
- do not infer pagination state from list length alone

## 4. Stable Resource Areas

### Studio

Purpose:

- manage reusable saved assets
- drive persistent product behavior

Main endpoints:

- `GET/POST /api/v1/studio/patterns`
- `GET/PATCH /api/v1/studio/patterns/{pattern_id}`
- `POST /api/v1/studio/patterns/from-selection`
- `GET/POST /api/v1/studio/entities`
- `GET/PATCH /api/v1/studio/entities/{entity_id}`
- `GET/POST /api/v1/studio/configurations`
- `GET/PATCH /api/v1/studio/configurations/{configuration_id}`
- `GET /api/v1/studio/search`

Stable frontend meaning:

- `patterns` are reusable matchers with optional default transformations
- `entities` are reusable custom detection assets
- `configurations` are saved packs, profiles, and presets
- search returns mixed result kinds across studio assets and jobs

### Jobs

Purpose:

- inspect persisted work
- apply review decisions
- read generated outputs

Main endpoints:

- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `POST /api/v1/jobs/{job_id}/review`

Stable frontend meaning:

- a `job` is the main persisted review unit
- findings belong to jobs
- outputs belong to jobs
- review updates happen at the job level

### Text Workflows

Main endpoints:

- `POST /api/v1/workflows/text/analyze`
- `POST /api/v1/workflows/text/transform`
- `POST /api/v1/workflows/text/analyze-transform`

Frontend guidance:

- treat `analyze` -> `review` -> `transform` as the primary UX flow
- treat `analyze-transform` as a convenience path, not the main review-first UI
- when transforming a persisted text job, resend `content`; raw source text is not
  retained by the backend

### Image Workflows

Main endpoints:

- `POST /api/v1/workflows/images/analyze`
- `POST /api/v1/workflows/images/transform`
- `POST /api/v1/workflows/images/transform-job`

Frontend guidance:

- these endpoints use `multipart/form-data`
- `manifest_json` is a JSON string field, not a nested JSON body
- for review-first UI, prefer `analyze` -> job review -> `transform-job`
- default image anonymization is `blur` when no explicit image transformation is
  provided

### Bulk Text Workflows

Main endpoints:

- `POST /api/v1/bulk/text/analyze`
- `GET /api/v1/bulk/jobs`
- `GET /api/v1/bulk/jobs/{bulk_id}`
- `POST /api/v1/bulk/jobs/{bulk_id}/review`
- `POST /api/v1/bulk/text/transform`

Stable frontend meaning:

- a `bulk job` is a persisted parent resource
- child text jobs are created for valid submitted items
- per-item outcomes are explicit and can partially fail
- ordering is deterministic and follows submitted item order

## 5. Review-First Product Rule

Obsura is review-first.

Frontend should model the main workflows like this:

1. analyze content
2. present findings
3. submit review decisions
4. transform/export after review

This applies to:

- single text flows
- image/screenshot flows
- bulk text flows

Do not design the main product UX around blind automatic transformation.

## 6. Findings, Decisions, and Summaries

Common review vocabulary:

- `pending`
- `approved`
- `rejected`

Common summary shape:

```json
{
  "total": 4,
  "pending": 1,
  "approved": 2,
  "rejected": 1
}
```

Frontend rules:

- use this summary shape across single-job and bulk UI
- drive review badges and counters from these values
- do not build separate ad-hoc count models for bulk and non-bulk screens

## 7. Output and File References

Important rule:

- file-related paths in API responses are storage-relative references, not host
  filesystem paths

Examples:

- `source_file_path`
- `stored_input_path`
- `stored_output_path`
- `output_file_path`

Frontend rules:

- do not display these as local machine paths
- do not assume they are directly fetchable URLs
- when `media_url` is present, use `media_url` for browser display
- treat storage-relative references as backend-managed identifiers
- source image references are intentionally not exposed back to the frontend
- generated image outputs are short-lived backend-managed artifacts, not durable
  files

## 8. Transformation Customization

The frontend can control anonymization style per finding or as a workflow default.

Text-focused fields:

- `mode`
- `placeholder`
- `mask_character`
- `prefix_visible`
- `suffix_visible`
- `semantic_label`
- `alias_prefix`

Image-focused fields:

- `mode`
- `blur_radius`
- `pixelation_scale`
- `region_padding`
- `overlay_shape`
- `overlay_corner_radius`
- `overlay_color`
- `outline_color`
- `outline_width`
- `overlay_label`
- `label_position`
- `label_font_family`
- `label_font_size`
- `label_color`
- `label_background_color`
- `label_padding`
- `label_margin`

Stable defaults:

- text default remains generic redaction, returning `[REDACTED]`
- image default is now `blur`
- image overlays do not render label text unless the frontend explicitly sends
  `overlay_label` or a placeholder-based mode
## 9. Recommended Frontend Client Structure

Use one typed API client layer with resource grouping similar to the backend:

- `healthApi`
- `studioApi`
- `jobsApi`
- `textWorkflowsApi`
- `imageWorkflowsApi`
- `bulkJobsApi`

Recommended client behavior:

- one shared response-envelope parser
- one shared error normalizer
- one shared pagination helper
- one shared UUID-based cache key strategy

Recommended type groups:

- envelope types
- pagination types
- studio asset types
- finding/review types
- job/output types
- text workflow request/response types
- image workflow request/response types
- bulk request/response types

## 10. Recommended UI Flows

### Single Text Flow

1. submit `POST /api/v1/workflows/text/analyze`
2. render findings from `data.findings`
3. submit `POST /api/v1/jobs/{job_id}/review`
4. submit `POST /api/v1/workflows/text/transform`
5. render `output_text` and replacement summary

### Screenshot/Image Flow

1. upload file to `POST /api/v1/workflows/images/analyze`
2. render returned regions/findings
3. submit review decisions through the related job
4. submit `POST /api/v1/workflows/images/transform-job`
5. use `media_url` when present to preview the generated output

### Bulk Text Flow

1. submit `POST /api/v1/bulk/text/analyze`
2. render bulk parent summary plus per-item outcomes
3. open child jobs for review or drive inline review UX
4. submit `POST /api/v1/bulk/jobs/{bulk_id}/review`
5. submit `POST /api/v1/bulk/text/transform`
6. render per-item transform outcomes explicitly

## 11. Known Limits the Frontend Must Respect

Current runtime limits can be configured, but frontend should assume these exist:

- upload byte limits
- image pixel limits
- bulk text item count limit
- bulk text per-item character limit
- bulk text total character limit

Frontend guidance:

- validate obvious size limits client-side where practical
- still rely on server validation as the source of truth
- surface server error messages directly in admin/operator UI

## 12. Postman and OpenAPI Usage

Available integration artifacts:

- repo root `openapi.json`
- repo root `postman.json`

Frontend team should use:

- `openapi.json` as the stable contract reference
- `postman.json` for manual workflow testing and QA reproduction

The Postman collection already supports:

- chained IDs for studio assets
- job and finding capture
- bulk run capture
- review-first flow testing

## 13. What Is Stable Enough To Build Against

Frontend can confidently build against:

- unified response and error envelope
- pagination contract
- studio asset CRUD/search
- persisted jobs and review
- text analyze/review/transform
- image analyze/review/transform-job
- bulk text analyze/review/transform
- readiness/version endpoints
- storage-relative file reference semantics

## 14. What Is Intentionally Deferred

Do not design frontend dependencies on these yet:

- bulk images
- bulk analyze-transform
- PDF/document workflows
- auth and workspace isolation
- background job orchestration
- export/reporting systems

## 15. Practical Integration Checklist

Before frontend integration starts:

1. import `openapi.json` into your API tooling if needed
2. use `/api/v1/ready` as the backend readiness gate
3. implement one shared response-envelope parser
4. implement one shared error formatter
5. model review findings and summaries once and reuse them
6. build review-first UX first, convenience flows second
