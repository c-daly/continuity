import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from memory_read_provider import MemoryObservation
from promotion import Cluster, Promotion, SourceRef
from synthesis_pass import is_cross_boundary, already_covered


def _obs(subject, name):
    return MemoryObservation(type="project", subject=subject, name=name, description="d")

def test_single_scope_is_not_cross_boundary():
    c = Cluster("x", [_obs("LOGOS", "1"), _obs("LOGOS", "2")])
    assert not is_cross_boundary(c)

def test_two_scopes_two_members_is_cross_boundary():
    c = Cluster("x", [_obs("LOGOS", "1"), _obs("agent-swarm", "2")])
    assert is_cross_boundary(c)

def test_one_member_not_cross_boundary():
    c = Cluster("x", [_obs("LOGOS", "1")])
    assert not is_cross_boundary(c)

def test_already_covered_subset_true():
    c = Cluster("x", [_obs("LOGOS", "1"), _obs("agent-swarm", "2")])
    existing = [Promotion(id="p", scope="", title="", statement="",
                          sources=[SourceRef("1", "LOGOS"), SourceRef("2", "agent-swarm"),
                                   SourceRef("3", "user")],
                          instances=3, created_at="2026-08-15")]
    assert already_covered(c, existing)

def test_grown_cluster_is_covered():
    # cluster grew (existing sources subset of members) -> covered in v1 (refinement is slice 2)
    c = Cluster("x", [_obs("LOGOS", "1"), _obs("agent-swarm", "2"), _obs("user", "9")])
    existing = [Promotion(id="p", scope="", title="", statement="",
                          sources=[SourceRef("1", "LOGOS"), SourceRef("2", "agent-swarm")],
                          instances=2, created_at="2026-08-15")]
    assert already_covered(c, existing)

def test_distinct_overlap_not_covered():
    # shares one member but neither set nests the other -> distinct concept -> promote
    c = Cluster("x", [_obs("LOGOS", "1"), _obs("user", "9")])
    existing = [Promotion(id="p", scope="", title="", statement="",
                          sources=[SourceRef("1", "LOGOS"), SourceRef("2", "agent-swarm")],
                          instances=2, created_at="2026-08-15")]
    assert not already_covered(c, existing)

def test_empty_sources_promotion_covers_nothing():
    c = Cluster("x", [_obs("LOGOS", "1"), _obs("agent-swarm", "2")])
    existing = [Promotion(id="p", scope="", title="", statement="",
                          sources=[], instances=0, created_at="2026-08-15")]
    assert not already_covered(c, existing)
