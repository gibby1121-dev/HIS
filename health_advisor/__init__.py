"""Health Advisor — a Jane-side, health-scoped reference layer over Kent's Vault.

Personal reference, NOT medical advice. Read the canonical Vault files before
answering or filing; answer from that material first; flag gaps instead of
inventing; file using the established conventions; write back to Drive.
"""

from .config import VaultConfig, load_config
from .glossary import Glossary, load_glossary
from .guardrails import guardrail_flags, GuardrailFlag
from .open_loops import OpenLoops, load_open_loops

__all__ = [
    "VaultConfig",
    "load_config",
    "Glossary",
    "load_glossary",
    "guardrail_flags",
    "GuardrailFlag",
    "OpenLoops",
    "load_open_loops",
]
