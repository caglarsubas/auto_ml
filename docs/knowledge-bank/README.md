# DeclarAI Knowledge Bank

This folder is the source of truth for platform guidance that the DeclarAI
assistant can retrieve during chat turns. The assistant uses these documents
when its intent classifier adds the `R` retrieval label to a user query.

## Documents

- `platform-guideline-user-manual.md` explains the platform flow, user-facing
  capabilities, dependencies between stages, settings, and assistant usage.
- `technical-disclosure.md` explains the data-science decisions, calculations,
  assumptions, and rationale behind each pipeline step.
- `terminology-glossary.md` defines the technical terms, metrics, abbreviations,
  and platform labels that users see in the product.
- `assistant-usage-and-action-guide.md` explains how to work with the assistant,
  including when it answers, when it retrieves knowledge, when it uses live
  pipeline tools, and when it proposes executable actions.
- `model-governance-review-checklist.md` gives a practical review checklist for
  analysts and validators before they rely on or export a model.

## Retrieval Contract

The knowledge bank is intentionally versioned with the application. It should
describe DeclarAI's actual behavior, not generic AutoML behavior. When a
workflow, calculation, threshold, or action path changes, update the relevant
knowledge-bank document in the same pull request as the product change.

The assistant retrieval layer chunks Markdown sections, ranks them with a
deterministic lexical scorer, and injects compact cited snippets into the chat
prompt only when the classifier includes `R`. This keeps ordinary status or
execution turns focused on live pipeline artifacts while still giving
documentation-grade answers for manual, glossary, and disclosure questions.
