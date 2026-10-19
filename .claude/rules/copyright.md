# Copyright and licensing policy (non-negotiable)

Applies to everything in the repo: code, knowledge base, data, prompts, tests, fixtures, examples and docs.

This is the owner's personal, public repository: viewed by recruiters, copied into the course repository for review, and possibly opened as open source later. Everything in it must be legally reusable and redistributable by anyone, without asking for permission. The owner chose this strict level on purpose; do not relax it without their explicit decision.

1. **Only open-licensed content.** Allowed: public domain, CC0, and CC BY (any version), or an equivalent licence that allows redistribution, derivatives and commercial use with attribution only.
2. **Everything that needs permission or a licence grant is excluded.** That includes: all rights reserved, "free to read" without a reuse licence, paywalled content, CC BY-NC, CC BY-ND, CC BY-NC-ND, share-alike database licences (ODbL), and any source whose licence we could not verify. Unknown licence = excluded.
3. **The approved list is `docs/SOURCES.md`.** Use nothing else in the knowledge base, prompts, tests, fixtures, examples or docs. Do not copy or closely paraphrase excluded sources. A plain link to an official page is not copying, but nothing from that page goes into the project.
4. **Adding a source** requires: reading the licence line on the publisher or article page itself (aggregator metadata alone is not enough), recording the licence, URL and check date in `docs/SOURCES.md`, and the owner's approval before it is used.
5. **Text only.** Do not extract figures, tables or images from articles. They may be reproduced from third parties under other terms.
6. **Attribution.** Keep `ATTRIBUTION.md` (authors, title, year, DOI/URL, licence link, "split into chunks" as the change made), generated from the source manifest. Every chunk carries `source_url`, `license`, `authors`, `year` metadata so the app can cite it.
7. **Raw documents are not committed by default.** Commit a manifest and a download script. Commit a text only when its row in `docs/SOURCES.md` is marked verified on the article itself.
8. **Code and dependencies.** Do not paste code, prompts or text from sources with an incompatible or unknown licence. Prefer permissively licensed libraries (MIT, BSD, Apache-2.0) and check a new dependency's licence before adding it. The repo's own code licence (if one is added) does not relicense the third-party content; each document keeps its own licence.
9. **When in doubt, stop and ask the owner.** This policy is a working rule, not legal advice; the owner makes the final call.
