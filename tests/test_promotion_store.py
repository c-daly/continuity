import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from vault_write_provider import VaultWriteProvider
from promotion import Promotion, SourceRef, promotion_to_frontmatter, PromotionStore


def _write(vault, p):
    VaultWriteProvider(vault_path=vault).write(
        "cont.promotion", p.id, promotion_to_frontmatter(p), p.statement)

def test_store_lists_live_promotions_only(tmp_path):
    (tmp_path / "10-projects" / "LOGOS").mkdir(parents=True)
    live = Promotion(id="a", scope="10-projects/LOGOS", title="A", statement="s",
                     sources=[SourceRef("n", "LOGOS")], instances=2, created_at="2026-08-15")
    dead = Promotion(id="b", scope="", title="B", statement="s",
                     sources=[SourceRef("n", "user")], instances=2, created_at="2026-08-15",
                     superseded_by="a")
    _write(tmp_path, live)
    _write(tmp_path, dead)
    ids = {p.id for p in PromotionStore(tmp_path).list()}
    assert ids == {"a"}
