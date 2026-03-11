"""Generate OpenAPI and Postman artifacts for Obsura API."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from obsura_api.app import create_app

COLLECTION_VARIABLES: list[tuple[str, str]] = [
    ("baseUrl", "http://localhost:8000"),
    ("searchQuery", "infra"),
    ("patternId", ""),
    ("entityId", ""),
    ("configurationId", ""),
    ("jobId", ""),
    ("findingId", ""),
    ("patternIdsJson", "[]"),
    ("entityIdsJson", "[]"),
    ("configurationIdsJson", "[]"),
    ("jobIdsJson", "[]"),
    ("findingIdsJson", "[]"),
    ("outputFilePath", ""),
    ("outputMediaUrl", ""),
]

PATH_VARIABLE_MAP = {
    "pattern_id": "patternId",
    "entity_id": "entityId",
    "configuration_id": "configurationId",
    "job_id": "jobId",
}

QUERY_VARIABLE_MAP = {
    "q": "searchQuery",
}

REQUEST_EXAMPLES: dict[tuple[str, str], dict[str, Any]] = {
    ("POST", "/api/v1/studio/patterns"): {
        "name": "Infrastructure Domain Pattern",
        "description": "Protect an internal domain across text workflows.",
        "category": "infrastructure",
        "tags": ["ops", "safe-share"],
        "is_active": True,
        "matcher": {
            "kind": "exact",
            "value": "internal.example.com",
            "case_sensitive": False,
            "applies_to": ["text", "structured_text"],
        },
        "transformation": {
            "mode": "semantic",
            "semantic_label": "INTERNAL_DOMAIN",
        },
        "scope": {"workspace": "default"},
    },
    ("PATCH", "/api/v1/studio/patterns/{pattern_id}"): {
        "description": "Updated description for the saved pattern.",
        "tags": ["ops", "reviewed"],
        "is_active": True,
    },
    ("POST", "/api/v1/studio/patterns/from-selection"): {
        "name": "Selected Internal Hostname",
        "selected_value": "vps-prod-01.internal",
        "description": "Created from a manual selection in a screenshot or pasted text.",
        "category": "hosts",
        "tags": ["selection", "ops"],
        "transformation": {
            "mode": "semantic",
            "semantic_label": "PRIVATE_HOST",
        },
        "applies_to": ["text", "structured_text"],
    },
    ("POST", "/api/v1/studio/entities"): {
        "name": "Customer Names",
        "description": "Protect known customer names with a stable alias.",
        "category": "customers",
        "tags": ["crm"],
        "is_active": True,
        "detection_definitions": [
            {
                "kind": "value_list",
                "values": ["Acme Corp", "Globex"],
                "case_sensitive": False,
                "applies_to": ["text", "structured_text"],
            }
        ],
        "transformation": {
            "mode": "stable_alias",
            "alias_prefix": "CUSTOMER",
        },
        "scope": {"workspace": "default"},
    },
    ("PATCH", "/api/v1/studio/entities/{entity_id}"): {
        "description": "Updated custom entity description.",
        "tags": ["crm", "reviewed"],
        "is_active": True,
    },
    ("POST", "/api/v1/studio/configurations"): {
        "kind": "pack",
        "name": "Infrastructure Safe-Share Pack",
        "description": "Reusable pack for terminal text, logs, and VPS screenshots.",
        "category": "infrastructure",
        "tags": ["ops", "preset"],
        "is_active": True,
        "pattern_ids": ["{{patternId}}"],
        "custom_entity_ids": ["{{entityId}}"],
        "default_text_transformation": {
            "mode": "semantic",
            "semantic_label": "SENSITIVE_VALUE",
        },
        "default_image_transformation": {
            "mode": "blur",
            "blur_radius": 10,
        },
        "face_preferences": {"mode": "blur", "blur_radius": 12},
        "metadata": {"team": "platform"},
    },
    ("PATCH", "/api/v1/studio/configurations/{configuration_id}"): {
        "description": "Updated preset description.",
        "tags": ["ops", "updated"],
        "metadata": {"team": "platform", "status": "reviewed"},
    },
    ("POST", "/api/v1/jobs/{job_id}/review"): {
        "decisions": [
            {
                "finding_id": "{{findingId}}",
                "decision": "approved",
                "transformation": {
                    "mode": "semantic",
                    "semantic_label": "INTERNAL_DOMAIN",
                },
            }
        ]
    },
    ("POST", "/api/v1/workflows/text/analyze"): {
        "title": "Terminal safe-share review",
        "content": "Connect to https://internal.example.com from 10.0.0.1 as root",
        "content_type": "text",
        "apply_builtins": True,
        "pattern_ids": ["{{patternId}}"],
        "custom_entity_ids": ["{{entityId}}"],
        "configuration_ids": ["{{configurationId}}"],
        "exact_values": ["root"],
        "manual_spans": [],
        "default_transformation": {
            "mode": "semantic",
            "semantic_label": "SENSITIVE_VALUE",
        },
        "persist_job": True,
        "persist_source_content": True,
    },
    ("POST", "/api/v1/workflows/text/transform"): {
        "job_id": "{{jobId}}",
        "finding_overrides": [
            {
                "finding_id": "{{findingId}}",
                "decision": "approved",
                "transformation": {
                    "mode": "semantic",
                    "semantic_label": "INTERNAL_DOMAIN",
                },
            }
        ],
        "include_pending": False,
        "persist_output": True,
    },
    ("POST", "/api/v1/workflows/text/analyze-transform"): {
        "title": "One-shot alias workflow",
        "content": "customer=acme customer=acme customer=globex",
        "content_type": "text",
        "apply_builtins": False,
        "exact_values": ["acme", "globex"],
        "default_transformation": {
            "mode": "stable_alias",
            "alias_prefix": "CUSTOMER",
        },
        "persist_job": False,
    },
    ("POST", "/api/v1/workflows/images/transform-job"): {
        "job_id": "{{jobId}}",
        "finding_overrides": [
            {
                "finding_id": "{{findingId}}",
                "decision": "approved",
                "transformation": {
                    "mode": "mask",
                    "overlay_color": "#111111",
                    "overlay_label": "REDACTED",
                },
            }
        ],
        "include_pending": False,
        "persist_output": True,
    },
}

FORM_EXAMPLES: dict[tuple[str, str], dict[str, str]] = {
    ("POST", "/api/v1/workflows/images/analyze"): {
        "manifest_json": json.dumps(
            {
                "title": "Screenshot region review",
                "content_type": "screenshot",
                "configuration_ids": ["{{configurationId}}"],
                "regions": [
                    {
                        "kind": "image_region",
                        "source": "manual",
                        "entity_type": "SECRET_REGION",
                        "entity_name": "Secret block",
                        "region": {"x": 48, "y": 24, "width": 240, "height": 96},
                        "transformation": {"mode": "blur", "blur_radius": 10},
                    }
                ],
                "detect_faces": False,
                "persist_job": True,
            },
            indent=2,
        ),
    },
    ("POST", "/api/v1/workflows/images/transform"): {
        "manifest_json": json.dumps(
            {
                "title": "Screenshot safe-share export",
                "content_type": "screenshot",
                "configuration_ids": ["{{configurationId}}"],
                "regions": [
                    {
                        "kind": "image_region",
                        "source": "manual",
                        "entity_type": "SECRET_REGION",
                        "entity_name": "API key panel",
                        "region": {"x": 48, "y": 24, "width": 240, "height": 96},
                        "transformation": {
                            "mode": "mask",
                            "overlay_color": "#111111",
                            "overlay_label": "REDACTED",
                        },
                    }
                ],
                "detect_faces": False,
                "persist_job": True,
            },
            indent=2,
        ),
    },
}

REQUEST_EXTRACTORS: dict[tuple[str, str], list[dict[str, Any]]] = {
    ("GET", "/api/v1/studio/patterns"): [
        {"variable": "patternId", "paths": [["data", 0, "id"]]},
        {"variable": "patternIdsJson", "paths": [["data", "__collect__", "id"]]},
    ],
    ("POST", "/api/v1/studio/patterns"): [
        {"variable": "patternId", "paths": [["data", "id"]]},
    ],
    ("GET", "/api/v1/studio/patterns/{pattern_id}"): [
        {"variable": "patternId", "paths": [["data", "id"]]},
    ],
    ("PATCH", "/api/v1/studio/patterns/{pattern_id}"): [
        {"variable": "patternId", "paths": [["data", "id"]]},
    ],
    ("GET", "/api/v1/studio/entities"): [
        {"variable": "entityId", "paths": [["data", 0, "id"]]},
        {"variable": "entityIdsJson", "paths": [["data", "__collect__", "id"]]},
    ],
    ("POST", "/api/v1/studio/entities"): [
        {"variable": "entityId", "paths": [["data", "id"]]},
    ],
    ("GET", "/api/v1/studio/entities/{entity_id}"): [
        {"variable": "entityId", "paths": [["data", "id"]]},
    ],
    ("PATCH", "/api/v1/studio/entities/{entity_id}"): [
        {"variable": "entityId", "paths": [["data", "id"]]},
    ],
    ("GET", "/api/v1/studio/configurations"): [
        {"variable": "configurationId", "paths": [["data", 0, "id"]]},
        {"variable": "configurationIdsJson", "paths": [["data", "__collect__", "id"]]},
    ],
    ("POST", "/api/v1/studio/configurations"): [
        {"variable": "configurationId", "paths": [["data", "id"]]},
    ],
    ("GET", "/api/v1/studio/configurations/{configuration_id}"): [
        {"variable": "configurationId", "paths": [["data", "id"]]},
    ],
    ("PATCH", "/api/v1/studio/configurations/{configuration_id}"): [
        {"variable": "configurationId", "paths": [["data", "id"]]},
    ],
    ("GET", "/api/v1/jobs"): [
        {"variable": "jobId", "paths": [["data", 0, "id"]]},
        {"variable": "jobIdsJson", "paths": [["data", "__collect__", "id"]]},
        {"variable": "findingId", "paths": [["data", 0, "findings", 0, "id"]]},
        {"variable": "outputFilePath", "paths": [["data", 0, "outputs", 0, "output_file_path"]]},
    ],
    ("GET", "/api/v1/jobs/{job_id}"): [
        {"variable": "jobId", "paths": [["data", "id"]]},
        {"variable": "findingId", "paths": [["data", "findings", 0, "id"]]},
        {"variable": "findingIdsJson", "paths": [["data", "findings", "__collect__", "id"]]},
        {"variable": "outputFilePath", "paths": [["data", "outputs", 0, "output_file_path"]]},
    ],
    ("POST", "/api/v1/jobs/{job_id}/review"): [
        {"variable": "jobId", "paths": [["data", "id"]]},
        {"variable": "findingId", "paths": [["data", "findings", 0, "id"]]},
        {"variable": "findingIdsJson", "paths": [["data", "findings", "__collect__", "id"]]},
    ],
    ("POST", "/api/v1/workflows/text/analyze"): [
        {"variable": "jobId", "paths": [["data", "job_id"]]},
        {"variable": "findingId", "paths": [["data", "findings", 0, "id"]]},
        {"variable": "findingIdsJson", "paths": [["data", "findings", "__collect__", "id"]]},
    ],
    ("POST", "/api/v1/workflows/text/transform"): [
        {"variable": "jobId", "paths": [["data", "job_id"]]},
    ],
    ("POST", "/api/v1/workflows/text/analyze-transform"): [
        {"variable": "jobId", "paths": [["data", "job_id"]]},
    ],
    ("POST", "/api/v1/workflows/images/analyze"): [
        {"variable": "jobId", "paths": [["data", "job_id"]]},
        {"variable": "findingId", "paths": [["data", "findings", 0, "id"]]},
        {"variable": "findingIdsJson", "paths": [["data", "findings", "__collect__", "id"]]},
    ],
    ("POST", "/api/v1/workflows/images/transform"): [
        {"variable": "jobId", "paths": [["data", "job_id"]]},
        {"variable": "findingId", "paths": [["data", "findings", 0, "id"]]},
        {"variable": "findingIdsJson", "paths": [["data", "findings", "__collect__", "id"]]},
        {"variable": "outputFilePath", "paths": [["data", "stored_output_path"]]},
        {"variable": "outputMediaUrl", "paths": [["data", "media_url"]]},
    ],
    ("POST", "/api/v1/workflows/images/transform-job"): [
        {"variable": "jobId", "paths": [["data", "job_id"]]},
        {"variable": "findingId", "paths": [["data", "findings", 0, "id"]]},
        {"variable": "findingIdsJson", "paths": [["data", "findings", "__collect__", "id"]]},
        {"variable": "outputFilePath", "paths": [["data", "stored_output_path"]]},
        {"variable": "outputMediaUrl", "paths": [["data", "media_url"]]},
    ],
}


def build_description(operation: dict[str, Any], notes: list[str] | None = None) -> str:
    """Build a readable Postman request description from OpenAPI metadata."""

    parts: list[str] = []
    summary = operation.get("summary")
    description = operation.get("description")
    if summary:
        parts.append(summary)
    if description and description != summary:
        parts.append(description)
    if notes:
        parts.append("Collection helpers:\n- " + "\n- ".join(notes))
    return "\n\n".join(parts)


def build_url(path: str, parameters: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert an OpenAPI path definition into a Postman URL object."""

    segments: list[str] = []
    query: list[dict[str, str]] = []

    for segment in path.strip("/").split("/"):
        if segment.startswith("{") and segment.endswith("}"):
            path_name = segment[1:-1]
            variable_name = PATH_VARIABLE_MAP.get(path_name, path_name)
            segments.append(f"{{{{{variable_name}}}}}")
        else:
            segments.append(segment)

    raw = "{{baseUrl}}/" + "/".join(segments)

    for parameter in parameters:
        if parameter.get("in") != "query":
            continue
        name = parameter["name"]
        variable_name = QUERY_VARIABLE_MAP.get(name, name)
        query.append(
            {
                "key": name,
                "value": f"{{{{{variable_name}}}}}",
                "description": parameter.get("description", ""),
            }
        )

    if query:
        raw += "?" + "&".join(f"{item['key']}={item['value']}" for item in query)

    return {
        "raw": raw,
        "host": ["{{baseUrl}}"],
        "path": segments,
        "query": query,
    }


def build_event_script(extractors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build a Postman test script that validates responses and captures useful IDs."""

    script_lines = [
        'pm.test("Response status is successful", function () {',
        "  pm.expect(pm.response.code).to.be.below(400);",
        "});",
        "",
        'const contentType = pm.response.headers.get("Content-Type") || "";',
        'if (!contentType.includes("application/json")) {',
        "  return;",
        "}",
        "",
        "const body = pm.response.json();",
        "const readPath = (value, path) => {",
        "  let current = value;",
        "  for (const segment of path) {",
        "    if (segment === '__collect__') {",
        "      if (!Array.isArray(current)) {",
        "        return undefined;",
        "      }",
        "      return current;",
        "    }",
        "    if (current === undefined || current === null) {",
        "      return undefined;",
        "    }",
        "    current = current[segment];",
        "  }",
        "  return current;",
        "};",
        "const collectPath = (value, path) => {",
        "  const markerIndex = path.indexOf('__collect__');",
        "  if (markerIndex === -1) {",
        "    return undefined;",
        "  }",
        "  const collectionTarget = readPath(value, path.slice(0, markerIndex));",
        "  if (!Array.isArray(collectionTarget)) {",
        "    return undefined;",
        "  }",
        "  const tail = path.slice(markerIndex + 1);",
        "  return collectionTarget",
        "    .map((entry) => readPath(entry, tail))",
        "    .filter((entry) => entry !== undefined && entry !== null && entry !== '');",
        "};",
        "const extractors = " + json.dumps(extractors, indent=2) + ";",
        "for (const extractor of extractors) {",
        "  let assigned = false;",
        "  for (const path of extractor.paths) {",
        "    const value = path.includes('__collect__') ? collectPath(body, path) : readPath(body, path);",
        "    if (value === undefined || value === null || value === '') {",
        "      continue;",
        "    }",
        "    const serialized = Array.isArray(value) ? JSON.stringify(value) : String(value);",
        "    pm.collectionVariables.set(extractor.variable, serialized);",
        "    assigned = true;",
        "    break;",
        "  }",
        "  if (assigned) {",
        '    console.log(`Set collection variable ${extractor.variable}`);',
        "  }",
        "}",
    ]
    return [
        {
            "listen": "test",
            "script": {
                "type": "text/javascript",
                "exec": script_lines,
            },
        }
    ]


def build_request_item(path: str, method: str, operation: dict[str, Any]) -> dict[str, Any]:
    """Create one Postman request item from an OpenAPI operation."""

    method_upper = method.upper()
    extractors = REQUEST_EXTRACTORS.get((method_upper, path), [])
    notes: list[str] = []
    if extractors:
        variable_names = ", ".join(extractor["variable"] for extractor in extractors)
        notes.append(f"Automatically updates collection variables: {variable_names}.")
    if "{pattern_id}" in path:
        notes.append("Uses the `patternId` collection variable in the request URL.")
    if "{entity_id}" in path:
        notes.append("Uses the `entityId` collection variable in the request URL.")
    if "{configuration_id}" in path:
        notes.append("Uses the `configurationId` collection variable in the request URL.")
    if "{job_id}" in path:
        notes.append("Uses the `jobId` collection variable in the request URL.")

    request: dict[str, Any] = {
        "method": method_upper,
        "header": [{"key": "Accept", "value": "application/json"}],
        "description": build_description(operation, notes),
        "url": build_url(path, operation.get("parameters", [])),
    }

    request_body = operation.get("requestBody", {})
    content = request_body.get("content", {})
    if "application/json" in content:
        request["header"].append({"key": "Content-Type", "value": "application/json"})
        payload = REQUEST_EXAMPLES.get((method_upper, path), {})
        request["body"] = {
            "mode": "raw",
            "raw": json.dumps(payload, indent=2),
            "options": {"raw": {"language": "json"}},
        }
    elif "multipart/form-data" in content:
        form_example = deepcopy(FORM_EXAMPLES.get((method_upper, path), {}))
        request["body"] = {
            "mode": "formdata",
            "formdata": [
                {"key": "file", "type": "file", "src": []},
                *[
                    {"key": key, "type": "text", "value": value}
                    for key, value in form_example.items()
                ],
            ],
        }

    item: dict[str, Any] = {
        "name": operation.get("summary") or f"{method_upper} {path}",
        "request": request,
        "response": [],
    }
    if extractors:
        item["event"] = build_event_script(extractors)
    return item


def build_postman_collection(openapi_document: dict[str, Any]) -> dict[str, Any]:
    """Create a Postman collection from the generated OpenAPI document."""

    tag_order = [tag["name"] for tag in openapi_document.get("tags", [])]
    tag_descriptions = {
        tag["name"]: tag.get("description", "")
        for tag in openapi_document.get("tags", [])
    }
    grouped_items: dict[str, list[dict[str, Any]]] = {tag: [] for tag in tag_order}

    for path, methods in openapi_document["paths"].items():
        for method, operation in methods.items():
            tag = operation.get("tags", ["General"])[0]
            grouped_items.setdefault(tag, []).append(
                build_request_item(path, method, operation),
            )

    folders: list[dict[str, Any]] = []
    for tag in tag_order:
        items = grouped_items.get(tag, [])
        if not items:
            continue
        folders.append(
            {
                "name": tag.replace("-", " ").title(),
                "description": tag_descriptions.get(tag, ""),
                "item": items,
            }
        )

    return {
        "info": {
            "name": "Obsura API",
            "description": (
                "Professional Postman collection for Obsura API.\n\n"
                "Quick start:\n"
                "1. Set `baseUrl` to your target deployment.\n"
                "2. Run create endpoints for patterns, entities, or configurations.\n"
                "3. The collection automatically captures IDs such as `patternId`, "
                "`configurationId`, `jobId`, and `findingId` from JSON responses.\n"
                "4. Follow the text or image workflow requests in order without manually copying IDs."
            ),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
            "_postman_id": "obsura-api-collection",
        },
        "variable": [
            {"key": key, "value": value, "type": "string"}
            for key, value in COLLECTION_VARIABLES
        ],
        "item": folders,
    }


def generate_artifacts(output_directory: Path | None = None) -> tuple[Path, Path]:
    """Generate `openapi.json` and `postman.json` into the target directory."""

    target_directory = output_directory or Path.cwd()
    target_directory.mkdir(parents=True, exist_ok=True)

    app = create_app()
    openapi_document = app.openapi()
    postman_collection = build_postman_collection(openapi_document)

    openapi_path = target_directory / "openapi.json"
    postman_path = target_directory / "postman.json"
    openapi_path.write_text(json.dumps(openapi_document, indent=2) + "\n", encoding="utf-8")
    postman_path.write_text(
        json.dumps(postman_collection, indent=2) + "\n",
        encoding="utf-8",
    )
    return openapi_path, postman_path


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for artifact generation."""

    parser = argparse.ArgumentParser(
        description="Generate OpenAPI and Postman artifacts for Obsura API.",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory where `openapi.json` and `postman.json` will be written.",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint for artifact generation."""

    args = parse_args()
    openapi_path, postman_path = generate_artifacts(Path(args.output_dir).resolve())
    print(f"Wrote {openapi_path}")
    print(f"Wrote {postman_path}")


if __name__ == "__main__":
    main()
