---
created: 2026-08-12
status: open
for: Iris
from: Rex
priority: low
---

# Committed, then edited in the working tree

This note is committed and then modified by the fixture builder, so its bytes on
disk no longer match any commit. Under the default citation gate it is skipped by
name; under `--allow-dirty` it is emitted stamped `meta.dirty`.
