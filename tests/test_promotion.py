import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from memory_read_provider import MemoryObservation
from promotion import (SourceRef, Cluster, PromotionDraft, Promotion,
                       promotion_to_frontmatter, promotion_id)


def _obs(subject, name):
    return MemoryObservation(type="project", subject=subject, name=name, description="d")

def test_cluster_subjects_distinct_sorted():
    c = Cluster(concept="x", members=[_obs("b", "1"), _obs("a", "2"), _obs("b", "3")])
    assert c.subjects() == ["a", "b"]

def test_promotion_id_is_slug():
    assert promotion_id("Always Parallelize Work!") == "always-parallelize-work"

def test_frontmatter_roundtrips_core_fields():
    p = Promotion(id="c", scope="10-projects/LOGOS", title="T", statement="S",
                  sources=[SourceRef("n1", "LOGOS"), SourceRef("n2", "sophia")],
                  instances=2, created_at="2026-08-15", supersedes=None)
    fm = promotion_to_frontmatter(p)
    assert fm["kind"] == "promotion"
    assert fm["scope"] == "10-projects/LOGOS"
    assert fm["title"] == "T"
    assert fm["instances"] == 2
    assert fm["created_at"] == "2026-08-15"
    assert fm["supersedes"] is None
    assert fm["superseded_by"] is None
    assert fm["sources"] == [{"name": "n1", "scope": "LOGOS"}, {"name": "n2", "scope": "sophia"}]
