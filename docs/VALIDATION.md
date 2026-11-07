# Validation record

Development session: 7 November 2026. Platform: Linux, Python 3.12.14. This distinguishes executed checks from configured CI and unavailable live services.

## Passed here

- Installed the package in an isolated virtual environment; `pip check` found no broken requirements.
- **28 offline tests** with `python -m unittest discover -s tests -v`: sustained-vs-spike ranking, no-evidence gate, duplicate evidence, international-vs-local separation, missing-market weighting, modpack discovery, new creator-format discovery, Google Trends partial-week removal, YouTube API parsing, Reddit intent, listing navigation/nesting, authorized imports, Discord privacy/permalinks, credential redaction, history timing/sample compatibility, demo/live isolation, local AI failure/citation validation, CSV formula protection, PDF/export generation, and HTTP host/origin/path boundaries.
- `python -m trendfinder demo` generated **96 synthetic observations**, 10 hypotheses and a **23-page English PDF**. `pdfinfo`, text extraction and rendered pages confirmed the report metadata, headings, evidence and template/cost sections. The committed example is labeled synthetic on every page.
- Chromium/Playwright browser checks: desktop plus 320px, 390px and 768px layouts; no horizontal overflow; format selection; source filtering; background demo scan; archive refresh; PDF download; no application JavaScript errors. Screenshot: `docs/dashboard-demo.png`.
- Python compilation and Git whitespace checks.
- Built a Python wheel, installed it into a separate directory, verified bundled dashboard assets, and generated a PDF from that installation outside the checkout.

## Live collection attempted, blocked

The managed cloud proxy returned HTTP CONNECT 403 for Modrinth, YouTube, Google Trends, Reddit, Craftlist, server lists and reporting feeds. A complete live scan produced zero observations, explicit per-source blocked/skipped diagnostics and an **INSUFFICIENT EVIDENCE** PDF. It exited with code 2, as designed. No synthetic values entered that live report or the live snapshot table.

Network-domain additions were saved to this chat's environment draft, preserving previous entries. They are not applied by saving the draft. Live collection must be rechecked after environment settings are saved or on the user's Windows machine with appropriate access. The code does not bypass the proxy or disable TLS verification.

## Not claimed as tested

- Native Windows setup, Task Scheduler and the Windows executable: Windows/Linux CI and a manual Windows build workflow are provided, but this Linux session cannot establish their results. Inspect Actions after pushing.
- Real API credentials, YouTube quota, private Discord permissions, authorized TikTok/Facebook feeds: no credentials/data sources were supplied. Fixture tests do not establish live access.
- Local Ollama generation, model availability or 4 GB GPU performance: no local model/GPU was available. Optional model failure and invalid citations are tested with mocks. The deterministic report is fully functional without AI.
- Server-template RAM budgets, player counts, pricing, conversion and retention: proposed pilot assumptions, not production benchmarks.

The runnable application's offline workflow is verified. Current market conclusions remain unverified until real source collection succeeds; the demo is solely a product/layout preview.
