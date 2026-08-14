# Demo — findings index

### F1 — Guard hook does not see `bash -c` re-entry (2026-07-05, Rex)

A command wrapped in `bash -c` reaches the shell without passing the matcher the
hook registers on. Documented rather than patched; the guard is a speed bump for
honest mistakes, not a sandbox.

### F2 — Lock files survive a crashed worktree (2026-07-11, Tess)

A persona that dies mid-task leaves its claim behind and the next session refuses
to start. Stale-claim expiry added.

### F3 — Release tags stopped matching the changelog (2026-07-30, Rex)

The changelog records four releases past the newest tag on the remote. The tag
step of the release workflow has not run since. Bookkeeping only; no code effect.

### F4 — An un-onboarded agent committed under the owner's identity (2026-08-04, Tess)

An agent that never went through onboarding pushed to `main`, and the commit
carries the owner's name and email. **Nothing in the repository distinguishes
work the owner did from work an agent did on the owner's behalf**, which means
the attribution the whole governance story rests on is not actually present in
the substrate. This changes the product thesis: "the repo answers who did what"
was true of labels and ledgers and false of commits. Promoted to a spike, then
to ADR-027.

### F5 — Export skips modified sources silently in table mode (2026-08-07, Rex)

Fixed in the same change; the skip list now prints under the table.
