# Evidence Writer

Evidence Writer is an evidence-bounded nonfiction writing pipeline. Version
0.1.0 now contains three deliberately separate layers:

- the frozen v0.1.3 Contract Core and deterministic policies;
- a thin, injected-handler Pipeline Runner with verified filesystem storage;
- a vendor-neutral provider protocol and an offline deterministic FakeProvider.

There is still no real Auditor, Adapter, Writer, or Final Review LLM logic.
There are no prompts, research runtime, capability selection, Reference Library
runtime, UI, database, RAG, CI/CD, or Production integration.

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
- The next phase remains blocked until `LLM_STAGE_IMPLEMENTATION AUTHORIZED`.
