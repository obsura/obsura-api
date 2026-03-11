# Obsura API Tooling

This document defines the approved tooling direction for `obsura-api`.

Obsura is not expected to depend on a single tool forever. The product should use the right open-source tools for the right workflow while keeping one coherent API experience.

## 1. Tooling Philosophy

Obsura should use proven open-source tools where they are strong and add product value through:
- orchestration
- reviewability
- custom detection
- custom transformation
- persistent studio assets
- reusable workflow composition

Obsura should not rebuild mature lower-level capabilities from scratch unless there is a clear product need.

## 2. Primary Toolchain

The approved primary MVP toolchain direction is:
- **Microsoft Presidio** for text detection and sanitization foundations
- **Tesseract OCR** as the baseline OCR engine for screenshots and image text
- **Pillow** and **OpenCV** for image-region transformation work
- an open-source face-detection layer in the **MediaPipe-class** category for face-region workflows

This is a multi-tool model by design. Obsura's value comes from combining tools into a reviewable, reusable workflow, not from pretending one library solves the whole product.

## 3. Core Redaction and Detection Tooling Direction

The approved core detection and sanitization direction is centered on **Microsoft Presidio**.

Presidio is the approved starting point because it supports:
- built-in text detections
- custom recognizers
- structured text workflows
- rule-based extensibility
- integration into a Python backend

Presidio is the primary detection layer, not the entire product. Obsura still needs its own API models, review logic, saved assets, and transformation system on top.

## 4. OCR Direction

OCR is required for screenshot-first and image-text workflows.

The approved baseline OCR direction for MVP is **Tesseract OCR**. It is approved because it is:
- open-source
- self-hostable
- practical for screenshots and technical text
- easy to integrate into a Python backend

OCR should be treated as a required complementary capability, not an optional add-on. The system must remain flexible enough to adopt additional OCR options later if quality demands it.

## 5. Image Transformation Direction

Obsura requires image-region processing beyond text replacement.

The approved baseline image-processing direction for MVP is:
- **Pillow** for practical image loading and manipulation
- **OpenCV** for region operations and transformation support

This tooling direction must enable:
- blur
- pixelation
- masks
- overlays
- region-based fills
- visual replacement behavior

## 6. Face Detection Direction

Face detection is an approved first-class tooling area for image workflows.

The approved direction is an open-source face-detection stack in the **MediaPipe-class** category, with support for:
- face detection
- reviewable face-region output
- compatibility with blur, pixelation, masking, and visual replacement
- a path toward subregion targeting such as eye-only workflows

For MVP, the face stack must be practical and self-hostable. It does not need to become a full biometric analysis system.

## 7. PDF Direction Later

PDF workflows are part of the later product direction but are not the first implementation priority.

Later PDF support should combine:
- text extraction for text-based PDFs
- OCR for scanned PDFs
- region-aware sanitization where needed
- safe PDF or derived output generation

PDF support is therefore approved as a later integrated pipeline, not an MVP blocker.

## 8. Complementary Tools Expected

The product is expected to rely on complementary supporting capabilities alongside the primary toolchain, including:
- exact-value matching
- regex or pattern-based matching
- custom recognizer definitions
- image asset handling
- region geometry handling
- metadata extraction where useful

Obsura may combine multiple open-source tools as long as the result remains coherent, maintainable, and self-hostable.

## 9. What Is Approved for MVP

The approved MVP tooling scope is:
- Presidio-based text detection and custom recognizer support
- exact-value and pattern-based detection
- Tesseract-based OCR for screenshots and image text
- Pillow and OpenCV for image-region transformations
- a practical open-source face detector for reviewable face regions

This MVP tooling scope is approved because it covers the first real product workflows:
- pasted text sanitization
- screenshot sanitization
- image-region protection
- face protection
- reusable custom detection
- reusable transformation behavior

## 10. What Is Deferred

The following tooling areas are intentionally deferred:
- advanced audio tooling
- advanced video tooling
- full enterprise document-governance stacks
- broad archive-processing stacks
- vendor-specific compliance integrations
- tool diversity for its own sake

## 11. Tool Selection Principles

When selecting or revising tooling, Obsura should prefer:
1. open-source friendliness
2. self-hostability
3. practical integration value
4. acceptable quality for technical and daily-use workflows
5. maintainability for a small team or solo maintainer
6. extensibility for custom detection and custom transformation

Obsura should avoid:
- unnecessary tool sprawl
- hype-driven choices
- brittle stacks that complicate self-hosting
- dependencies that undermine the persistent studio model

## 12. Approved Tooling Statement

The current approved tooling direction for `obsura-api` is:
- Presidio as the primary text-detection and sanitization foundation
- Tesseract as the baseline OCR layer
- Pillow and OpenCV as the baseline image-transformation layer
- an open-source face-detection layer for face-region workflows
- later PDF and document tooling as an extension, not an MVP requirement

Obsura's value is defined by how these tools are orchestrated into a review-first, reusable, studio-like product model.
