# Evidence Writer

Evidence Writer is an evidence-bounded nonfiction writing pipeline. Version
0.1.0 now contains three deliberately separate layers:

- the frozen v0.1.3 Contract Core and deterministic policies;
- a thin, injected-handler Pipeline Runner with verified filesystem storage;
- a vendor-neutral provider protocol and an offline deterministic FakeProvider.

The authorized v0.1.0 LLM stage layer implements Auditor, Adapter, Writer, and
Final Review over an OpenAI-compatible Responses API. The frozen Contract Core,
Runner, serialization, authorization matrix, and Production boundary are
unchanged. There is no research search, topic selection, RAG, database, Web UI,
multi-agent runtime, Gold Corpus, or Author Model.

## Requirements

- Python 3.11+

## Install and verify

    python -m venv .venv
    . .venv/bin/activate
    pip install -e .
    python -m unittest discover -s tests -v

The full suite retains every Contract Core regression and adds serialization,
pipeline stop-state, storage read-back, provider isolation, and CLI coverage. It
does not require a network connection or API key.

## Contract serialization boundary

Every model or Python value must pass through
`evidence_writer.serialization.to_contract_json` before JCS or SHA-256.
`canonical_json` and `canonical_sha256` use that entry automatically. Stage
implementations must not hash Python repr, YAML text, formatted JSON, or private
stage-specific serialization.

## CLI

Validate the frozen complete-chain example:

    evidence-writer validate schema_examples/complete_chain.valid.yaml

Run the synthetic pipeline:

    evidence-writer run examples/synthetic_run.yaml

A successful run reports `status=COMPLETE`, the terminal stage, error code,
and artifact paths. It writes:

    output/synthetic/
      01_writer_handoff.json
      02_writer_input.json
      03_draft.json
      04_review.json
      final.md

The run command uses only configured synthetic StageResults. It performs no
network call and contains no real writing behavior.

## Real minimal run

Set the four required environment variables (their values are never printed):

    EVIDENCE_WRITER_LLM_API_KEY
    EVIDENCE_WRITER_LLM_BASE_URL
    EVIDENCE_WRITER_LLM_MODEL
    EVIDENCE_WRITER_LLM_TIMEOUT_SECONDS

Then run:

    evidence-writer run-llm examples/real_minimal.yaml

This first performs a minimal provider connectivity request. Only after it
succeeds does the real Auditor → Adapter → Writer → Final Review pipeline run.
The Writer request contains only the frozen `WriterInput`; Final Review receives
that evidence boundary and the Draft and can only PASS, LOCAL_REPAIR, or
RETURN_TO_WRITER. A successful run writes the same five verified artifacts as
the synthetic runner, including `output/first-real-article/final.md`.

## Runner stop semantics

Only a fully validated PASS artifact can reach the next injected handler. FAIL,
BLOCKED, invalid Contract data, invalid digest/provenance, deterministic-policy
failure, provider error, or storage read-back failure stops execution. The
Runner never calls downstream handlers after that point and emits formal
BLOCKED StageResults for every remaining stage.

## Boundaries

- Production assets are not read, written, mounted, or synchronized.
- WriterHandoff is the only evidence authority available to a future Writer.
- Author Intent and Capability have no fact authority.
- Reference Library is not a runtime dependency.
- Modern copyrighted material defaults to link-only/no-quote.
- Provider runtime configuration is read only from the four documented
  `EVIDENCE_WRITER_LLM_*` environment variables.

## Public-source flu-prevention example

`examples/flu_prevention.yaml` is a complete, offline Contract fixture. Validate
its deterministic policy ingress without invoking a model:

    PYTHONPATH=src python -m unittest tests.test_examples -v

The example deliberately treats its only source as `LINK_ONLY`. Material
attributed to《中国流感疫苗预防接种技术指南（2025—2026）》is scoped only to the
2025—2026 influenza season. Because one secondary popular-science source cannot
independently verify vaccine supply or a national free-vaccination policy for
the 2026—2027 season, the fixture carries that constraint as an explicit LIMIT
and a dependent FORBIDDEN claim rather than presenting either item as verified
fact or current national policy.
