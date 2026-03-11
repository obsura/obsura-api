# Obsura API Requirements

## Status

This document defines the frozen functional product requirements for `obsura-api`.

It specifies:
- the product purpose of the API layer
- the workflows and assets the API must support
- the boundaries of the first product definition
- the product truths future implementation must preserve

This document is intentionally implementation-neutral. It does not choose frameworks, libraries, transport details, or deployment mechanics.

## 1. Purpose

`obsura-api` is the workflow and orchestration core of Obsura.

Its purpose is to let users and clients:
- submit text, screenshots, and images for analysis
- detect sensitive or protected content
- define what should count as sensitive for their own context
- review and adjust findings before output is produced
- apply safe redaction or transformation behavior
- generate safe, shareable output
- save, organize, search, and reuse detection and transformation assets over time

Obsura is not limited to simple redaction. The API must support a broader sanitization model that includes:
- text sanitization
- screenshot sanitization
- image sanitization
- face protection
- custom detection
- reusable packs, profiles, and presets
- transformation workflows
- persistent studio-like saved assets

## 2. Product Role

`obsura-api` is the source of truth for:
- detection behavior
- reviewable findings
- transformation decisions
- reusable user-defined rules
- persistent studio assets
- output generation
- repeatable sanitization workflows
- job and run history

The API powers clients and user interfaces, but it is not itself the primary end-user interface.

## 3. Primary Goals

The API must enable Obsura to achieve these primary goals:

1. Safe sharing of text, screenshots, and images.
2. Review-first workflows instead of blind automation.
3. First-class built-in and custom detection.
4. First-class transformation beyond plain placeholder replacement.
5. Reuse through saved packs, profiles, presets, and assets.
6. Trustworthy, understandable output.
7. Persistent studio organization for ongoing work.
8. Strong support for practical technical and daily-use workflows.

## 4. Product Principles

### 4.1 Users define their own sensitivity model

The system must not assume a fixed universal entity list is enough. Users must be able to define organization-specific, project-specific, and personal protection logic.

### 4.2 Review before release

Detection and transformation may be assisted by tooling, but the product direction is review-first. The API must preserve enough structure for clients to support inspection, approval, rejection, and adjustment before export.

### 4.3 Detection and transformation are separate concerns

What is detected and how it is transformed are different decisions. The API must model them separately so users can reuse detection logic with different transformation behavior.

### 4.4 Studio persistence matters

Obsura is not only a one-shot sanitization endpoint. The API must support a persistent studio model where users can define, save, organize, search, and reuse their own assets.

### 4.5 Technical and daily-use workflows are primary

The initial product direction must work well for repeated practical cases such as:
- VPS screenshots
- terminal output
- logs
- structured text
- screenshots that contain text, faces, or sensitive regions
- shareable artifacts used in issue trackers, chats, tickets, and documentation

### 4.6 Open-source and self-hosted friendliness

The product direction must remain compatible with an open-source, self-hosted system. Requirements must favor portability and practical deployment over vendor-shaped assumptions.

## 5. In-Scope Content Categories

### 5.1 Initial priority content

The first product scope must prioritize:
- plain text
- pasted text
- logs
- shell output
- JSON
- YAML
- XML
- HTML-like text
- screenshots
- images containing text
- images containing faces
- images containing sensitive regions or labels

### 5.2 Later content families

The following are later priorities and not initial blockers:
- PDF
- DOCX
- PPTX
- XLSX
- scanned documents
- email-like exports
- archive bundles

## 6. Core Feature Groups

### 6.1 Content intake and workflow classification

The API must support:
- text submission
- image submission
- structured text-like submission
- workflows that combine built-in detections, custom detections, and manual review

The API must preserve enough information to determine:
- content type
- applicable workflow
- applicable detection sources
- applicable transformation types

### 6.2 Detection

The API must support detection through:
- built-in detection
- custom detection
- exact-value protection
- value lists
- reusable patterns
- custom entities
- packs, profiles, and presets
- future inferred or generalized detection

Detection must be applicable across:
- text
- structured text
- text extracted from screenshots or images
- image regions
- faces and face-related regions
- future document workflows

### 6.3 Custom Detection

Custom detection is a mandatory first-class feature.

The API must allow users to define what should be detected and protected for their own context.

Custom detection must support:
- exact fixed values
- lists of values
- pattern-based matching
- named custom entities
- reusable detection sets
- per-user customization
- future project or workspace scoping
- distinguishable provenance from built-in detection

Representative examples include:
- internal domains
- hostnames
- VPS usernames
- project names
- customer names
- internal URLs
- repeated identifiers
- company-specific tokens
- exact strings selected from real content

### 6.4 Packs, Profiles, and Presets

The API must support reusable configurations that users can apply repeatedly.

These reusable assets may combine:
- detection rules
- exact-value lists
- custom entities
- transformation defaults
- review defaults
- face protection preferences
- image-region protection styles

Representative examples include:
- infrastructure pack
- screenshot safe-share preset
- public share pack
- face privacy profile
- company-specific pack

### 6.5 Review Support

The API must support review-first workflows.

It must provide enough information for a client to:
- show what was detected
- show where it was detected
- show whether it came from built-in logic, custom logic, or manual input
- show the matched entity or region class
- allow approval or rejection
- allow transformation changes before export
- allow manual adjustments
- retain review decisions for the job history

### 6.6 Manual Selection Support

The API must support manual protection decisions in addition to automatic detection.

This includes:
- manually selected text
- manually selected exact values
- manually selected image regions
- manually selected face-like regions
- manually chosen replacements
- manually chosen image-region transformations

### 6.7 Transformation Engine

The API must support a first-class transformation engine.

Obsura is not limited to generic placeholder replacement. The transformation layer must support configurable, reusable, and reviewable protection behavior for text and image-like content.

Core rule:
- sensitive content must be securely protected before presentation-oriented output is produced

The API must preserve a distinction between:
- secure protection behavior
- transformation behavior
- presentation behavior

### 6.8 Transformation Modes

The API must support, at minimum, the following transformation modes.

#### A. Generic text replacement

Examples:
- `[REDACTED]`
- `[HIDDEN]`

#### B. Semantic text replacement

Examples:
- `[PRIVATE_HOST]`
- `[INTERNAL_DOMAIN]`
- `[CUSTOMER_NAME]`

#### C. User-defined replacement text

Examples:
- project-specific labels
- organization-defined placeholders
- custom review labels

#### D. Derived replacement

The API must support transformation values derived from the original content.

Examples:
- first character only
- last character only
- first and last character
- preserved prefix
- preserved suffix
- masked middle
- initials
- transformed aliases

#### E. Consistent alias replacement

The API should support stable aliases for repeated values within an applicable scope.

Examples:
- `CUSTOMER_A`
- `CUSTOMER_B`
- the same hostname becoming the same alias throughout a job or saved configuration

#### F. Inline visual replacement

Examples:
- inline tag
- inline badge
- styled label

#### G. Region-based visual replacement

Examples:
- solid block
- rounded block
- labeled overlay
- icon-and-label overlay
- custom fill or pattern

#### H. Blur-based transformation

Blur must be a first-class transformation mode.

This includes:
- adjustable blur intensity
- reusable blur profiles
- region-based blur
- face-based blur
- eye-only blur where relevant

#### I. Pixelation-based transformation

Pixelation must be a first-class transformation mode.

This includes:
- adjustable pixelation strength
- reusable pixelation profiles
- region-based pixelation
- face-based pixelation

#### J. Mask and overlay transformation

Examples:
- solid color overlay
- shaped mask
- line-based mask
- colored fill
- branded or named mask style

#### K. Image or texture replacement

The API must support replacement of a protected region with image-like or asset-like content where appropriate.

### 6.9 Layout-Aware Transformation

The API must support transformation behavior that preserves usefulness and readability where possible.

For text-like content, transformation behavior should preserve:
- readable flow
- usable spacing
- approximate structure
- terminal-like readability where relevant

For image-like content, transformation behavior should preserve where appropriate:
- region alignment
- visual proportion
- composition
- scaling that remains coherent within the transformed area

### 6.10 Face Detection and Face-Region Protection

Face detection is a first-class capability for image workflows.

The API must support:
- detecting faces in images
- representing faces as reviewable regions
- applying transformation behavior to faces
- saving reusable face-protection preferences in profiles or presets

Face workflows must support:
- full-face redaction
- full-face blur
- full-face pixelation
- face masking
- face replacement with visual overlays or assets

The product must also be designed to support more specific face-region targeting where relevant.

Representative subregions include:
- eyes only
- upper face
- lower face
- manually defined facial subregions

### 6.11 Persistent Studio Model

`obsura-api` must support a persistent studio model.

The product must support a reusable, organized, searchable working environment where users can define, manage, and reuse sanitization assets over time.

Persistent storage must exist for:
- custom patterns
- custom entities
- rule groups
- packs, profiles, and presets
- replacement definitions
- transformation definitions
- blur profiles
- mask profiles
- visual assets
- categories
- tags
- saved jobs or runs
- user preferences
- future project or workspace organization

### 6.12 Pattern Management

Each saved pattern must support, at minimum:
- name
- description
- active or inactive state
- category
- tags
- detection behavior
- transformation behavior
- relevant scope metadata

Patterns must be:
- searchable
- reusable
- editable
- removable
- usable alone or inside larger packs, profiles, or presets

### 6.13 Custom Entity Management

Each saved custom entity must support:
- name
- description
- one or more detection definitions
- one or more transformation behaviors
- grouping within categories or packs
- reuse across multiple jobs

### 6.14 Search and Discovery

The API must support search across stored studio assets.

Users must be able to search or filter for:
- patterns
- custom entities
- packs, profiles, and presets
- transformation assets
- categories
- tags
- jobs and runs

Search must support, at minimum:
- name-based lookup
- description-based lookup
- category filtering
- tag filtering
- active or inactive filtering where relevant

### 6.15 Job and Run History

The API must support persistent records of sanitization jobs or runs.

A job or run must be able to retain:
- title or label
- submission context
- content type
- applied patterns or packs
- applied transformation profiles
- detected items
- review decisions
- resulting output metadata
- created and updated timestamps
- future notes or review metadata

### 6.16 Pattern-from-Selection

The API must support workflows where:
- a user selects a value from text or extracted content
- the system treats it as an exact sensitive value
- the user can save it as reusable protection logic
- the value can be added to a named pattern, entity, pack, or preset

### 6.17 Exact-Value Protection

The API must support direct exact-value protection.

A user must be able to say:
- protect this exact string
- protect this list of strings
- always protect these values in this saved scope

### 6.18 Readability Preservation

For text-like content, the API must support output that remains useful after protection.

This means preserving:
- understandable structure
- enough readability for review or discussion
- meaningful placeholders where useful
- compositional stability where transformation is visual

### 6.19 Output Generation

The API must support generation of safe output appropriate to the content type.

This includes:
- sanitized text
- sanitized structured text
- sanitized image output
- later sanitized document output

Output must prioritize:
- safety
- clarity
- readability
- practical shareability

### 6.20 Verification Support

The API must preserve enough workflow information to support:
- confirmation of what was protected
- confidence in the resulting output
- future verification and audit-oriented features

## 7. Priority Order

### Priority 1

The first execution phase must prioritize:
- text analysis and protection
- screenshot and image text protection
- built-in detection
- custom detection
- exact-value protection
- reusable packs, profiles, and presets
- review-ready findings
- safe transformed output
- persistent studio assets
- the transformation engine
- blur and pixelation for image regions
- face detection support
- face transformation support

### Priority 2

The second layer of product depth should include:
- richer review controls
- better semantic replacement behavior
- stronger technical-content presets
- improved structured-text workflows
- pattern-from-selection flows
- saved custom entity sets
- richer visual replacement styles
- region-specific face transformations
- saved transformation asset libraries

### Priority 3

Later product expansion may include:
- document-family workflows
- broader file support
- advanced verification workflows
- deeper workspace or project collaboration
- broader ecosystem concepts

## 8. Success Criteria

`obsura-api` is successful when Obsura clients can support workflows such as:
- "Hide all sensitive values in this terminal screenshot before I share it."
- "Protect these exact internal domains every time."
- "Use my saved infrastructure pack on this log output."
- "Let me review detections before export."
- "Use semantic replacement for domains but blur faces."
- "Protect only the eye area in this image."
- "Turn this selected value into a reusable pattern."
- "Show me my past runs and how the output was produced."

## 9. Freeze Statement

The following product truths are frozen for `obsura-api`:
- it is the workflow and orchestration core of Obsura
- it must support text-first and screenshot-first workflows
- it must support built-in detection and custom detection
- it must support exact-value protection
- it must support reusable patterns, packs, profiles, and presets
- it must support persistent studio assets and search across them
- it must support review-first workflows
- it must support transformation behavior beyond plain text replacement
- it must support blur, pixelation, masking, and visual replacement for image regions
- it must support face detection and face-protection workflows
- it must support job and run history
- it must remain useful for practical technical and daily-use content
- it must produce safe, shareable output
