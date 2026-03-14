"""Generate OpenAPI and Postman artifacts for Obsura API."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from obsura_api.app import create_app
from obsura_api.core.settings import get_settings

COLLECTION_VARIABLES: list[tuple[str, str]] = [
    ("baseUrl", "http://localhost:8000"),
    ("searchQuery", "infra"),
    ("page", "1"),
    ("page_size", "20"),
    ("patternId", ""),
    ("entityId", ""),
    ("configurationId", ""),
    ("bulkId", ""),
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
    "bulk_id": "bulkId",
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
            "applies_to": ["text", "structured_text", "document", "csv"],
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
        "applies_to": ["text", "structured_text", "document", "csv"],
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
                "applies_to": ["text", "structured_text", "document", "csv"],
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
        "pii_detection": {
            "language": "en",
            "entity_allow_list": ["EMAIL_ADDRESS", "IP_ADDRESS", "PERSON"],
            "context_words": ["customer", "email", "server"],
        },
        "face_preferences": {"mode": "blur", "blur_radius": 12},
        "metadata": {"team": "platform"},
    },
    ("PATCH", "/api/v1/studio/configurations/{configuration_id}"): {
        "description": "Updated preset description.",
        "tags": ["ops", "updated"],
        "pii_detection": {
            "context_words": ["customer", "contact", "email"],
        },
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
    ("POST", "/api/v1/bulk/text/analyze"): {
        "title": "Bulk terminal safe-share review",
        "content_type": "text",
        "apply_builtins": True,
        "pattern_ids": ["{{patternId}}"],
        "custom_entity_ids": ["{{entityId}}"],
        "configuration_ids": ["{{configurationId}}"],
        "pii_detection": {
            "language": "en",
            "entity_allow_list": ["EMAIL_ADDRESS", "URL"],
            "context_words": ["login", "customer", "contact"],
        },
        "exact_values": ["root", "admin"],
        "persist_source_content": False,
        "items": [
            {
                "client_item_id": "snippet-1",
                "title": "VPS login output",
                "content": "ssh root@10.0.0.5",
            },
            {
                "client_item_id": "snippet-2",
                "title": "Internal URL sample",
                "content": "curl https://internal.example.com/login",
            },
            {
                "client_item_id": "snippet-3",
                "title": "Intentional invalid item",
                "content": "   ",
            },
        ],
    },
    ("POST", "/api/v1/bulk/jobs/{bulk_id}/review"): {
        "jobs": [
            {
                "job_id": "{{jobId}}",
                "decisions": [
                    {
                        "finding_id": "{{findingId}}",
                        "decision": "approved",
                    }
                ],
            }
        ]
    },
    ("POST", "/api/v1/bulk/text/transform"): {
        "bulk_id": "{{bulkId}}",
        "job_overrides": [
            {
                "job_id": "{{jobId}}",
                "content": "token=secret",
                "finding_overrides": [
                    {
                        "finding_id": "{{findingId}}",
                        "decision": "approved",
                    }
                ],
            }
        ],
        "include_pending": False,
        "persist_output": True,
    },
    ("POST", "/api/v1/workflows/text/analyze"): {
        "title": "Terminal safe-share review",
        "content": "Connect to https://internal.example.com from 10.0.0.1 as root",
        "content_type": "text",
        "apply_builtins": True,
        "pattern_ids": ["{{patternId}}"],
        "custom_entity_ids": ["{{entityId}}"],
        "configuration_ids": ["{{configurationId}}"],
        "pii_detection": {
            "language": "en",
            "entity_allow_list": ["EMAIL_ADDRESS", "URL", "IP_ADDRESS"],
            "context_words": ["customer", "support", "server"],
        },
        "exact_values": ["root"],
        "manual_spans": [],
        "default_transformation": {
            "mode": "semantic",
            "semantic_label": "SENSITIVE_VALUE",
        },
        "persist_job": True,
        "persist_source_content": False,
    },
    ("POST", "/api/v1/workflows/text/transform"): {
        "job_id": "{{jobId}}",
        "content": "Connect to https://internal.example.com from 10.0.0.1 as root",
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
        "title": "One-shot hashed secret workflow",
        "content": "token=alpha token=alpha",
        "content_type": "text",
        "apply_builtins": False,
        "exact_values": ["alpha"],
        "default_transformation": {
            "mode": "hash",
        },
        "persist_job": False,
    },
    ("POST", "/api/v1/workflows/csv/transform-job"): {
        "job_id": "{{jobId}}",
        "finding_overrides": [
            {
                "finding_id": "{{findingId}}",
                "decision": "approved",
            }
        ],
        "include_pending": False,
        "persist_output": True,
    },
    ("POST", "/api/v1/workflows/structured/analyze"): {
        "title": "Customer profile review",
        "data": {
            "customer": {
                "email": "john@example.com",
                "id": "CUST-123",
            },
            "contacts": [
                {
                    "phone": "+1 202-555-0123",
                }
            ],
        },
        "apply_builtins": True,
        "persist_job": True,
    },
    ("POST", "/api/v1/workflows/structured/transform"): {
        "title": "Structured one-shot export",
        "data": {
            "customer": {
                "email": "john@example.com",
                "token": "secret",
            }
        },
        "exact_values": ["secret"],
        "persist_job": False,
    },
    ("POST", "/api/v1/workflows/structured/transform-job"): {
        "job_id": "{{jobId}}",
        "data": {
            "customer": {
                "email": "john@example.com",
                "id": "CUST-123",
            }
        },
        "finding_overrides": [
            {
                "finding_id": "{{findingId}}",
                "decision": "approved",
            }
        ],
        "include_pending": False,
        "persist_output": True,
    },
    ("POST", "/api/v1/workflows/documents/transform-job"): {
        "job_id": "{{jobId}}",
        "finding_overrides": [
            {
                "finding_id": "{{findingId}}",
                "decision": "approved",
            }
        ],
        "include_pending": False,
        "persist_output": True,
    },
    ("POST", "/api/v1/workflows/images/transform-job"): {
        "job_id": "{{jobId}}",
        "finding_overrides": [
            {
                "finding_id": "{{findingId}}",
                "decision": "approved",
                "transformation": {
                    "mode": "blur",
                    "blur_radius": 12,
                    "region_padding": 6,
                    "outline_color": "#ff4d4f",
                    "outline_width": 2,
                },
            }
        ],
        "include_pending": False,
        "persist_output": True,
    },
}

FORM_EXAMPLES: dict[tuple[str, str], dict[str, str]] = {
    ("POST", "/api/v1/workflows/csv/analyze"): {
        "manifest_json": json.dumps(
            {
                "title": "Customer export review",
                "pattern_ids": ["{{patternId}}"],
                "custom_entity_ids": ["{{entityId}}"],
                "configuration_ids": ["{{configurationId}}"],
                "pii_detection": {
                    "language": "en",
                    "entity_allow_list": ["EMAIL_ADDRESS", "PERSON"],
                    "context_words": ["customer", "email", "contact"],
                },
                "apply_builtins": True,
                "has_header": True,
                "persist_job": True,
            },
            indent=2,
        ),
    },
    ("POST", "/api/v1/workflows/csv/transform"): {
        "manifest_json": json.dumps(
            {
                "title": "Customer export transform",
                "pattern_ids": ["{{patternId}}"],
                "custom_entity_ids": ["{{entityId}}"],
                "configuration_ids": ["{{configurationId}}"],
                "pii_detection": {
                    "language": "en",
                    "entity_allow_list": ["EMAIL_ADDRESS", "PERSON"],
                    "context_words": ["customer", "email", "contact"],
                },
                "apply_builtins": True,
                "exact_values": ["secret"],
                "has_header": True,
                "persist_job": True,
            },
            indent=2,
        ),
    },
    ("POST", "/api/v1/workflows/csv/transform-job"): {
        "manifest_json": json.dumps(
            {
                "job_id": "{{jobId}}",
                "finding_overrides": [
                    {
                        "finding_id": "{{findingId}}",
                        "decision": "approved",
                    }
                ],
                "include_pending": False,
                "persist_output": True,
            },
            indent=2,
        ),
    },
    ("POST", "/api/v1/workflows/documents/analyze"): {
        "manifest_json": json.dumps(
            {
                "title": "Customer contract review",
                "pattern_ids": ["{{patternId}}"],
                "custom_entity_ids": ["{{entityId}}"],
                "configuration_ids": ["{{configurationId}}"],
                "pii_detection": {
                    "language": "en",
                    "entity_allow_list": ["EMAIL_ADDRESS", "PERSON"],
                    "context_words": ["customer", "contract", "contact"],
                },
                "apply_builtins": True,
                "persist_job": True,
            },
            indent=2,
        ),
    },
    ("POST", "/api/v1/workflows/documents/transform"): {
        "manifest_json": json.dumps(
            {
                "title": "Customer contract export",
                "pattern_ids": ["{{patternId}}"],
                "custom_entity_ids": ["{{entityId}}"],
                "configuration_ids": ["{{configurationId}}"],
                "pii_detection": {
                    "language": "en",
                    "entity_allow_list": ["EMAIL_ADDRESS", "PERSON"],
                    "context_words": ["customer", "contract", "contact"],
                },
                "exact_values": ["secret"],
                "apply_builtins": True,
                "persist_job": True,
            },
            indent=2,
        ),
    },
    ("POST", "/api/v1/workflows/documents/transform-job"): {
        "manifest_json": json.dumps(
            {
                "job_id": "{{jobId}}",
                "finding_overrides": [
                    {
                        "finding_id": "{{findingId}}",
                        "decision": "approved",
                    }
                ],
                "include_pending": False,
                "persist_output": True,
            },
            indent=2,
        ),
    },
    ("POST", "/api/v1/workflows/images/analyze"): {
        "manifest_json": json.dumps(
            {
                "title": "Screenshot region review",
                "content_type": "screenshot",
                "configuration_ids": ["{{configurationId}}"],
                "pattern_ids": ["{{patternId}}"],
                "custom_entity_ids": ["{{entityId}}"],
                "pii_detection": {
                    "language": "en",
                    "entity_allow_list": ["PERSON", "EMAIL_ADDRESS"],
                    "context_words": ["customer", "email", "contact"],
                },
                "apply_builtins": True,
                "detect_text": True,
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
                "pattern_ids": ["{{patternId}}"],
                "custom_entity_ids": ["{{entityId}}"],
                "pii_detection": {
                    "language": "en",
                    "entity_allow_list": ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"],
                    "context_words": ["customer", "contact", "support"],
                },
                "apply_builtins": True,
                "detect_text": True,
                "regions": [
                    {
                        "kind": "image_region",
                        "source": "manual",
                        "entity_type": "SECRET_REGION",
                        "entity_name": "API key panel",
                        "region": {"x": 48, "y": 24, "width": 240, "height": 96},
                        "transformation": {
                            "mode": "overlay",
                            "overlay_color": "#111111",
                            "overlay_label": "REDACTED",
                            "overlay_shape": "rounded_rectangle",
                            "overlay_corner_radius": 12,
                            "region_padding": 8,
                            "outline_color": "#f97316",
                            "outline_width": 2,
                            "label_position": "outside_bottom",
                            "label_font_family": "mono",
                            "label_font_size": 18,
                            "label_background_color": "#111111",
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
    ("GET", "/api/v1/bulk/jobs"): [
        {"variable": "bulkId", "paths": [["data", 0, "id"]]},
    ],
    ("GET", "/api/v1/bulk/jobs/{bulk_id}"): [
        {"variable": "bulkId", "paths": [["data", "id"]]},
        {"variable": "jobId", "paths": [["data", "items", 0, "job_id"]]},
        {"variable": "jobIdsJson", "paths": [["data", "items", "__collect__", "job_id"]]},
    ],
    ("POST", "/api/v1/bulk/text/analyze"): [
        {"variable": "bulkId", "paths": [["data", "id"]]},
        {"variable": "jobId", "paths": [["data", "items", 0, "job_id"]]},
        {"variable": "jobIdsJson", "paths": [["data", "items", "__collect__", "job_id"]]},
    ],
    ("POST", "/api/v1/bulk/jobs/{bulk_id}/review"): [
        {"variable": "bulkId", "paths": [["data", "bulk_id"]]},
        {"variable": "jobId", "paths": [["data", "items", 0, "job_id"]]},
    ],
    ("POST", "/api/v1/bulk/text/transform"): [
        {"variable": "bulkId", "paths": [["data", "bulk_id"]]},
        {"variable": "jobId", "paths": [["data", "items", 0, "job_id"]]},
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
    ("POST", "/api/v1/workflows/csv/analyze"): [
        {"variable": "jobId", "paths": [["data", "job_id"]]},
        {"variable": "findingId", "paths": [["data", "findings", 0, "id"]]},
        {"variable": "findingIdsJson", "paths": [["data", "findings", "__collect__", "id"]]},
    ],
    ("POST", "/api/v1/workflows/csv/transform"): [
        {"variable": "jobId", "paths": [["data", "job_id"]]},
        {"variable": "findingId", "paths": [["data", "findings", 0, "id"]]},
        {"variable": "findingIdsJson", "paths": [["data", "findings", "__collect__", "id"]]},
    ],
    ("POST", "/api/v1/workflows/csv/transform-job"): [
        {"variable": "jobId", "paths": [["data", "job_id"]]},
        {"variable": "findingId", "paths": [["data", "findings", 0, "id"]]},
        {"variable": "findingIdsJson", "paths": [["data", "findings", "__collect__", "id"]]},
    ],
    ("POST", "/api/v1/workflows/documents/analyze"): [
        {"variable": "jobId", "paths": [["data", "job_id"]]},
        {"variable": "findingId", "paths": [["data", "findings", 0, "id"]]},
        {"variable": "findingIdsJson", "paths": [["data", "findings", "__collect__", "id"]]},
    ],
    ("POST", "/api/v1/workflows/documents/transform"): [
        {"variable": "jobId", "paths": [["data", "job_id"]]},
        {"variable": "findingId", "paths": [["data", "findings", 0, "id"]]},
        {"variable": "findingIdsJson", "paths": [["data", "findings", "__collect__", "id"]]},
    ],
    ("POST", "/api/v1/workflows/documents/transform-job"): [
        {"variable": "jobId", "paths": [["data", "job_id"]]},
        {"variable": "findingId", "paths": [["data", "findings", 0, "id"]]},
        {"variable": "findingIdsJson", "paths": [["data", "findings", "__collect__", "id"]]},
    ],
    ("POST", "/api/v1/workflows/structured/analyze"): [
        {"variable": "jobId", "paths": [["data", "job_id"]]},
        {"variable": "findingId", "paths": [["data", "findings", 0, "id"]]},
        {"variable": "findingIdsJson", "paths": [["data", "findings", "__collect__", "id"]]},
    ],
    ("POST", "/api/v1/workflows/structured/transform"): [
        {"variable": "jobId", "paths": [["data", "job_id"]]},
        {"variable": "findingId", "paths": [["data", "findings", 0, "id"]]},
        {"variable": "findingIdsJson", "paths": [["data", "findings", "__collect__", "id"]]},
    ],
    ("POST", "/api/v1/workflows/structured/transform-job"): [
        {"variable": "jobId", "paths": [["data", "job_id"]]},
        {"variable": "findingId", "paths": [["data", "findings", 0, "id"]]},
        {"variable": "findingIdsJson", "paths": [["data", "findings", "__collect__", "id"]]},
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
    if "{bulk_id}" in path:
        notes.append("Uses the `bulkId` collection variable in the request URL.")
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
                "`configurationId`, `bulkId`, `jobId`, and `findingId` from JSON responses.\n"
                "4. Follow the text, CSV, document, structured, or image workflow requests in order without manually copying IDs.\n"
                "5. Bulk text requests follow the review-first order: analyze -> get child job -> review -> transform.\n"
                "6. CSV exports in this collection are formula-safe and should be used as the download source.\n"
                "7. PDF document examples use multipart upload plus `manifest_json` and require resubmitting the file for reviewed transforms.\n"
                "8. Bulk text responses keep parent bulk state and per-item outcomes separate.\n"
                "9. Structured workflow examples include nested JSON payloads for field-level review.\n"
                "10. Image workflow examples include OCR-ready `manifest_json` payloads for screenshot testing."
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

    app = create_app(get_settings().model_copy(update={"auto_create_schema": True}))
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
