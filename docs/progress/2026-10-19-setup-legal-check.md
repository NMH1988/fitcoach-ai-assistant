[Progress log](../PROGRESS.md)

## 2026-10-19 · Legal check of sources and access terms · direct commit (no ticket, before the setup ticket)
- **Brief:** beyond the brief (owner's request): the copyright policy.
- **What:** `.claude/rules/copyright.md`: attribution now keeps the article's copyright and licence notices and implies no endorsement; new rule 7 (do not distort sources; leave out third-party content inside articles); new rule 10 (access terms: automated downloads only through the Europe PMC REST API or PMC's OAI-PMH/FTP/Cloud services; reading, saving or copying a single CC BY article by hand is allowed). `docs/SOURCES.md`: how the licences were checked, the access terms of PMC, Europe PMC and Taylor & Francis, and a summary of the CC BY 4.0 and 2.0 legal codes. `docs/ARCHITECTURE.md`: the download script uses only the Europe PMC REST API.
- **Why:** the owner asked for confirmation that reading, saving and copying the sources breaks no law or licence.
- **Decisions & gotchas:** the licence check on 2026-10-19 read 20 PMC article pages with a short script, which PMC's terms forbid (automated retrieval from its website). Only licence lines were read and no article text was stored; recorded in `docs/SOURCES.md`, and rule 10 prevents a repeat.
- **Follow-ups:** none.
