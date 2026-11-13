# ADR-0004: badminton-poc stays separate. Integration is a versioned file contract

Status: Accepted · 2026-11-12

## Context
badminton-poc (Python 3.11, YOLO11-pose, ByteTrack, TrackNetV3) already passes data between stages as files and writes `analysis.json`. Its measured state: Milestone 1 passed on development clips. Shot classification is at 0.59 accuracy across three recordings, against a 0.75 target.

## Decision
- No code dependency in either direction. Badminton Scout will consume an `analysis.json` that carries a `schema_version`, defined when CV enters scope (roadmap R5), not before.
- Only metrics with a measured accuracy above an agreed threshold are shown to users, printed with that accuracy. Shot types, tactics and weaknesses are excluded until validated.
- badminton-poc has no LICENSE file. Its owner adds one before any code or weights are redistributed.
