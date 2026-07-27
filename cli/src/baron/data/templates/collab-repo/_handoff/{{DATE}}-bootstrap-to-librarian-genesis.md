---
created: {{YYYY-MM-DD}}
status: open
for: librarian
from: bootstrap
priority: low
---

# Librarian — genesis acknowledgment

One-time bootstrap handoff. Created by `barony (runtime-agnostic path)` at scaffold time. After the Librarian processes this once, the standard cycle takes over.

## Why this exists

The skill seeded `wiki/log.md` and `wiki/index.md` at scaffold time so your `find -newer wiki/log.md` cycle has a real timestamp baseline from day one — but you (the Librarian) should still acknowledge the bootstrap so the team can see your first cycle ran successfully.

## What to do

1. **Read your `AGENT.md`** and `FAILOVER.md` end-to-end (the canonical operating manual). If anything is unclear, drop a `_handoff/ for: @{{OWNER_HANDLE}}` with the specific question — do not assume.
2. **Verify the wiki is well-formed:**
   - `wiki/log.md` has the genesis entry (one paragraph at the top)
   - `wiki/index.md` lists the standard sections (Log, Entities, Concepts, Sources)
   - `wiki/entities/`, `wiki/concepts/`, `wiki/sources/` exist (may be empty directories or scaffold READMEs)
3. **Run the standard cycle check** (`find findings/ decisions/ _handoff/ -name "*.md" -newer wiki/log.md`). Expect: this handoff and possibly nothing else, depending on team activity.
4. **Flip this handoff's `status: open` → `status: done`.**
5. **Commit + push** per your standard cycle:
   ```bash
   git add _handoff/{{DATE}}-bootstrap-to-librarian-genesis.md
   git commit -m "librarian: handoff | acknowledge genesis"
   git push origin main
   ```
6. **(Optional)** drop a `_handoff/ for: @{{OWNER_HANDLE}}` confirming you're operational and noting anything that needs project-owner attention (mismatched runtime fields, ambiguous AGENT.md sections, etc. — surface, don't auto-fix).

## What never happens

- Do not edit `wiki/log.md`'s genesis entry as part of this handoff. Genesis is genesis; future log entries are prepended.
- Do not act on this handoff a second time. If you see it with `status: done`, skip.
- Do not write outside `wiki/` and `_handoff/` per your scope.
