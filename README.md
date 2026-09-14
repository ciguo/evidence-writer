# Evidence Writer

Evidence Writer is an evidence-bounded nonfiction writing pipeline. This first
implementation slice contains only the frozen v0.1.3 Contract Core:

- Pydantic Contract models;
- deterministic policy validation;
- RFC 8785-compatible canonical JSON for the frozen Contract domain;
- SHA-256 artifact provenance checks;
- executable valid and negative Contract fixtures.

It intentionally contains **no** Runner, Provider, Auditor runtime, Writer
runtime, Final Review runtime, Web UI, database, RAG, or Production integration.

## Requirements

- Python 3.11+

## Install and verify

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
python -m unittest discover -s tests -v
```

The suite validates the valid contract chain, the 17 declared negative fixtures,
empty boundary fallback, digest/provenance integrity, embedded WriterHandoff
identity, independent validation of every PASS artifact, schema/model parity,
and failure-stage fail-closed behavior.

Raw JSON/YAML data must enter through `validate_contract_data` (or the raising
`ensure_contract_data_valid` helper). The ingress first applies the strict
v0.1.3 Pydantic Contract models and only then runs deterministic policy checks;
callers must not bypass this boundary by constructing unchecked objects.

## Boundaries

- Production assets are not read, written, mounted, or synchronized.
- WriterHandoff is the only evidence authority available to a future Writer.
- Author Intent and Capability have no fact authority.
- Reference Library is not a runtime dependency.
- Modern copyrighted material defaults to link-only/no-quote.

The next implementation phase is intentionally blocked pending code audit.
