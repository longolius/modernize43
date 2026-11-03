# Blank DCE project starter

Copy this directory into a **new project** and fill its `docs/` files in story-first order. Do not copy the Taskboard business content into new projects.

The blank starter is intentionally incomplete, not ready to BUILD or approve.

1. Describe a concrete user goal and smallest useful current scope in `docs/PROJECT.md`.
2. Describe observable user scenarios in `docs/STORIES.md`; use stable S-xx IDs.
3. Link every normative R-xx requirement to a C-xx component owner and A-xx acceptance ID.
4. Specify independent and negative acceptance oracles (O-xx), inputs, outputs and failure behavior.
5. Draw the public flow in Mermaid; record dependencies and external inputs in `docs/ARCHITECTURE.md`.
6. Record unresolved decisions in `docs/DECISIONS.md`. Do not silently resolve material ambiguity.
7. Create `docs/project-index.json` based on the **shape** of `docs/project-index.template.json`, delete the template filename and replace all placeholders.
8. Maintain complete *current* docs after each EVOLVE, rather than appending historical-only deltas.
9. Run `python3 tools/validate_docs.py PATH_TO_PROJECT` from this repository checkout. Passing is a preparation check only, not an approval.

Approval, Git provenance, code generation, agent orchestration, full gates and baseline promotion happen outside the starter and require explicit DCE execution contracts.
