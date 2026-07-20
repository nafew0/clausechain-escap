import os

# The judged test suite runs offline (no keys, no network, no LLM): every test —
# including the run.py subprocess test, which inherits this env — uses stub mode.
os.environ.setdefault("CLAUSECHAIN_PIPELINE", "stub")
os.environ.setdefault("GRAPH_BACKEND", "sqlite")
