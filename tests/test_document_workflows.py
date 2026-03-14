from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from obsura_api.app import create_app
from obsura_api.core.settings import Settings


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").replace("\n", "\\n")


def _build_pdf(*page_texts: str) -> bytes:
    object_ids: list[int] = [1, 2]
    font_id = 3 + (len(page_texts) * 2)
    objects: dict[int, bytes] = {
        1: b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        2: (
            "2 0 obj\n<< /Type /Pages /Kids ["
            + " ".join(f"{3 + (index * 2)} 0 R" for index in range(len(page_texts)))
            + f"] /Count {len(page_texts)} >>\nendobj\n"
        ).encode("latin-1"),
    }

    for index, page_text in enumerate(page_texts):
        page_id = 3 + (index * 2)
        content_id = page_id + 1
        object_ids.extend([page_id, content_id])
        content_stream = (
            "BT\n/F1 12 Tf\n72 720 Td\n(" + _escape_pdf_text(page_text) + ") Tj\nET"
        ).encode("latin-1")
        objects[page_id] = (
            f"{page_id} 0 obj\n"
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>\nendobj\n"
        ).encode("latin-1")
        objects[content_id] = (
            f"{content_id} 0 obj\n<< /Length {len(content_stream)} >>\nstream\n".encode("latin-1")
            + content_stream
            + b"\nendstream\nendobj\n"
        )

    object_ids.append(font_id)
    objects[font_id] = (
        f"{font_id} 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    ).encode("latin-1")

    ordered_ids = sorted(object_ids)
    parts: list[bytes] = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets: dict[int, int] = {}
    current_offset = len(parts[0])
    for object_id in ordered_ids:
        offsets[object_id] = current_offset
        item = objects[object_id]
        parts.append(item)
        current_offset += len(item)

    xref_offset = current_offset
    xref = [f"xref\n0 {len(ordered_ids) + 1}\n".encode("latin-1"), b"0000000000 65535 f \n"]
    for object_id in ordered_ids:
        xref.append(f"{offsets[object_id]:010} 00000 n \n".encode("latin-1"))

    trailer = (
        f"trailer\n<< /Size {len(ordered_ids) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("latin-1")
    return b"".join(parts + xref + [trailer])


@pytest.fixture
def document_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'obsura.db'}",
        storage_root=tmp_path / "storage",
        auto_create_schema=True,
        document_extractor_backend="pypdf",
        ocr_backend="noop",
        face_detector_backend="noop",
        pii_backend="noop",
        _env_file=None,
    )
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


def test_document_analyze_returns_page_aware_findings(document_client: TestClient) -> None:
    pdf_bytes = _build_pdf("Contact john@example.com for review")

    response = document_client.post(
        "/api/v1/workflows/documents/analyze",
        files={"file": ("review.pdf", pdf_bytes, "application/pdf")},
        data={"manifest_json": json.dumps({"persist_job": False})},
    )

    assert response.status_code == 200
    body = response.json()["data"]
    email_finding = next(
        item for item in body["findings"] if item["entity_type"] == "EMAIL_ADDRESS"
    )
    assert body["page_count"] == 1
    assert body["pages"][0]["page_number"] == 1
    assert email_finding["metadata"]["document_kind"] == "pdf"
    assert email_finding["metadata"]["document_page_number"] == 1
    assert email_finding["metadata"]["document_page_label"] == "Page 1"
    assert email_finding["metadata"]["document_page_text_hash"]


def test_document_transform_redacts_without_persisting_raw_pdf(document_client: TestClient) -> None:
    pdf_bytes = _build_pdf("Contact john@example.com token=secret")

    response = document_client.post(
        "/api/v1/workflows/documents/transform",
        files={"file": ("transform.pdf", pdf_bytes, "application/pdf")},
        data={"manifest_json": json.dumps({"exact_values": ["secret"]})},
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["output_text"]
    assert "[EMAIL]" in body["output_text"]
    assert "[REDACTED]" in body["output_text"]
    assert body["pages"][0]["output_text"]
    assert body["summary"]["replacement_count"] == 2

    job_response = document_client.get(f"/api/v1/jobs/{body['job_id']}")
    assert job_response.status_code == 200
    job = job_response.json()["data"]
    assert job["content_type"] == "document"
    assert job["source_file_path"] is None
    assert job["outputs"][0]["output_text"] is None
    assert job["outputs"][0]["metadata"]["document_kind"] == "pdf"


def test_document_review_and_transform_job_requires_matching_pdf(
    document_client: TestClient,
) -> None:
    original_pdf = _build_pdf("Contact john@example.com for review")

    analyze_response = document_client.post(
        "/api/v1/workflows/documents/analyze",
        files={"file": ("review.pdf", original_pdf, "application/pdf")},
        data={"manifest_json": json.dumps({})},
    )
    assert analyze_response.status_code == 200
    analysis = analyze_response.json()["data"]

    review_response = document_client.post(
        f"/api/v1/jobs/{analysis['job_id']}/review",
        json={
            "decisions": [
                {
                    "finding_id": finding["id"],
                    "decision": "approved",
                }
                for finding in analysis["findings"]
            ]
        },
    )
    assert review_response.status_code == 200

    transform_response = document_client.post(
        "/api/v1/workflows/documents/transform-job",
        files={"file": ("review.pdf", original_pdf, "application/pdf")},
        data={"manifest_json": json.dumps({"job_id": analysis["job_id"]})},
    )
    assert transform_response.status_code == 200
    transformed = transform_response.json()["data"]
    assert "[EMAIL]" in transformed["output_text"]

    changed_pdf = _build_pdf("Contact jane@example.com for review")
    mismatch_response = document_client.post(
        "/api/v1/workflows/documents/transform-job",
        files={"file": ("review.pdf", changed_pdf, "application/pdf")},
        data={"manifest_json": json.dumps({"job_id": analysis["job_id"]})},
    )
    assert mismatch_response.status_code == 422
    assert "does not match the reviewed job" in mismatch_response.json()["error"]["message"]


def test_document_analyze_rejects_pdf_without_extractable_text(document_client: TestClient) -> None:
    blank_pdf = _build_pdf("")

    response = document_client.post(
        "/api/v1/workflows/documents/analyze",
        files={"file": ("blank.pdf", blank_pdf, "application/pdf")},
        data={"manifest_json": json.dumps({"persist_job": False})},
    )

    assert response.status_code == 422
    assert "extractable text" in response.json()["error"]["message"]
