"""Status snapshot: open loops + anything pending a Drive write.

    python -m health_advisor
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .config import load_config
from .open_loops import load_open_loops

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def main() -> None:
    cfg = load_config()
    loops = load_open_loops()

    print(f"Vault: {cfg.vault_folder_id}  (owner {cfg.owner})")
    print(f"Canonical files: {len(cfg.files)}\n")

    ref = cfg.references
    if ref.stale_id_in_master and ref.stale_id_in_master != ref.id:
        print("! MASTER source index still points Health_References.md at the")
        print(f"  stale id {ref.stale_id_in_master}; live is {ref.id}. Reconcile.\n")

    print("Open loops:")
    print(loops.summary())

    pending_path = DATA_DIR / "pending_writes.yaml"
    pending = (yaml.safe_load(pending_path.read_text()) or {}).get("pending") or []
    if pending:
        print("\nPending Drive writes (commit when writes are restored):")
        for p in pending:
            print(f"- {p['id']} -> {p['target_file']} (captured {p['captured_on']})")


if __name__ == "__main__":
    main()
