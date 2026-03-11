# Obsura API Scenarios

This document translates the product requirements for `obsura-api` into realistic user scenarios.

These scenarios are not implementation steps. They describe the workflows the API must make possible for clients and future contributors.

## 1. VPS Screenshot Safe-Share

### Situation

A user takes a screenshot from a VPS session and wants to share it in a public issue, forum, or chat.

### Sensitive content may include

- IP addresses
- usernames
- hostnames
- internal domains
- prompt handles
- internal URLs
- container names
- image names
- project-specific identifiers

### Expected workflow

- submit the screenshot
- run built-in and custom detection against extracted text and image regions
- review findings before export
- optionally add manual regions or exact values
- export a safe image quickly

### Expected result

A shareable screenshot with sensitive content protected while preserving readability.

## 2. Pasted Terminal Text Sanitization

### Situation

A user pastes terminal output into Obsura before sharing it in a ticket, issue, or team chat.

### Expected workflow

- submit pasted text
- detect built-in technical entities
- apply custom patterns and exact-value protection
- review all findings
- choose semantic, generic, or custom replacement behavior
- export sanitized text

### Expected result

Readable terminal text that is safer to share and still useful for discussion.

## 3. Saved Infrastructure Pack

### Situation

A user repeatedly needs to hide the same infrastructure details across screenshots, logs, and pasted text.

### Expected workflow

- create a reusable pack
- include patterns for internal domains, hostnames, usernames, image names, and project codes
- save transformation defaults
- apply the saved pack to future jobs with minimal setup

### Expected result

A repeatable safe-share workflow for technical artifacts instead of rebuilding rules each time.

## 4. Custom Exact-Value Protection

### Situation

A user knows specific values that must always be protected, even if generic detectors would miss them.

### Representative values

- internal domains
- customer names
- project codes
- deployment handles
- static tokens

### Expected workflow

- add exact values manually
- save them in a reusable library
- apply them repeatedly in future jobs
- update them over time as the environment changes

### Expected result

Reliable protection for organization-specific content that would otherwise slip through.

## 5. Pattern-from-Selection

### Situation

A user sees a value in submitted content and wants to turn that real example into reusable protection logic.

### Expected workflow

- select a value from text or an extracted finding
- mark it as sensitive for the current job
- optionally save it as an exact-value rule, pattern, or custom entity
- optionally add it to a pack or preset

### Expected result

The user's studio library grows from real workflow usage instead of separate manual setup.

## 6. Face Blur Workflow

### Situation

A user uploads an image containing people and wants privacy protection without hiding the rest of the scene.

### Expected workflow

- detect faces
- present each face as a reviewable region
- apply blur with a chosen intensity or saved profile
- export the protected image

### Expected result

A privacy-preserving image suitable for sharing.

## 7. Eye-Only Protection Workflow

### Situation

A user wants selective privacy, such as blurring only the eyes instead of the full face.

### Expected workflow

- detect or define face subregions
- target only the eye area or upper-face region
- apply blur, pixelation, or masking
- review the result before export

### Expected result

Selective privacy handling with tighter presentation control.

## 8. Visual Replacement Workflow

### Situation

A user wants more expressive output than plain `[REDACTED]` placeholders.

### Expected workflow

- detect sensitive text or regions
- choose semantic placeholders, inline labels, overlays, or saved visual styles
- preserve readability and layout where possible
- export safe output that still looks intentional

### Expected result

Protected output that is clear, readable, and not limited to raw black-box redaction.

## 9. Stable Alias Workflow

### Situation

A user wants repeated values to stay distinguishable without exposing the original values.

### Example

The same customer name should always become the same alias within the relevant scope.

### Expected workflow

- detect repeated values
- apply stable alias logic within a job or saved configuration
- preserve distinction between different original values

### Expected result

Safer collaboration while keeping narrative continuity in the sanitized output.

## 10. Studio Search Workflow

### Situation

A user has accumulated many patterns, custom entities, packs, presets, and transformation profiles.

### Expected workflow

- search by name or description
- filter by category or tag
- quickly locate the right saved asset
- reuse it without rebuilding logic from scratch

### Expected result

A manageable studio experience rather than an unstructured list of saved rules.

## 11. Job History Workflow

### Situation

A user needs to reopen or inspect a previous sanitization run.

### Expected workflow

- view past jobs or runs
- inspect detections and review decisions
- see which pack, profile, or preset was applied
- understand how the final output was produced

### Expected result

Repeatability and trust across recurring workflows.

## 12. Mixed Detection Plus Transformation Workflow

### Situation

A user wants different handling for different findings in the same job.

### Example mapping

- domains -> semantic replacement
- hostnames -> partial masking
- faces -> blur
- a specific project code -> exact redaction

### Expected workflow

- run built-in and custom detection together
- review findings by type
- assign different transformation behavior per entity or region
- export a single coherent output

### Expected result

Obsura behaves like a real sanitization studio rather than a single-rule redaction utility.
