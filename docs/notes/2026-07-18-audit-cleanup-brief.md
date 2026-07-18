# Brief — repo audit + cleanup (2026-07-18)

Leo's request, verbatim (via /planbatch):

> can you review all the code and make sure the tests ran as accurately as possible. Also, clean up all planning files that are unused and reorganize and make claude.md more concise and get rid of any unnecessary info. Clean up any unused code as well and make sure phase 3 ran with the most accuracy possible.

Numbered items (for plan traceability):

1. Review all the code.
2. Make sure the tests ran as accurately as possible.
3. Clean up all planning files that are unused.
4. Reorganize and make CLAUDE.md more concise; get rid of any unnecessary info.
5. Clean up any unused code.
6. Make sure Phase 3 ran with the most accuracy possible.

**Addition (Leo, 2026-07-18, same day):** "please note this repo will be open source and public so organize the repo accordingly. also, the api key is not stored in the frontend right or exposed at all." → 7. Organize for a public/open-source audience. 8. Verify the API key is never stored or exposed anywhere in the repo. (Verified at capture: `git grep` for key-shaped strings across all 34,158 tracked files → 0 matches; no `.env` files; key lives only in macOS Keychain → env var at run time; LLM caches store prompt/response/model/token-counts only. There is no frontend yet — Phase 4 not started; its web demo must render committed run artifacts statically, with no live API key anywhere client-side.)

Context notes at capture time: repo is at `main`, clean, post-`phase3.2` Stage 3/4 completion (commits `0e64e6e6`, `9e623a51`); all Phase ≤3.3 work complete; next milestone is Phase 4. Leo first tried `/ultrareview` (needs a diff vs main — none existed), then routed the ask through `/planbatch`.
