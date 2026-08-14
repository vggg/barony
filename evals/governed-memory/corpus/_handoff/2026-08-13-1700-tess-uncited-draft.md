---
created: 2026-08-13
status: open
for: Vikram
from: Tess
priority: high
---

# Draft that was never committed — the bad/missing source-SHA case

The fixture builder writes this file and never adds it to git. It has no commit
to cite, so `baron export` skips it under every flag. It exists to prove that an
artifact which is real on disk and invisible to the corpus shows up as human
intervention tax rather than as an uncited record.

It also carries an answer nobody can retrieve: the enrolment gate should be a
CODEOWNERS rule on the signers file.
