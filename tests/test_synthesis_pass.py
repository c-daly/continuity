import sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from memory_read_provider import MemoryObservation
from promotion import Cluster, PromotionDraft, Clusterer, Drafter, PromotionStore
from vault_write_provider import VaultWriteProvider
from synthesis_pass import run_synthesis


class FakeReader:
    def __init__(self, obs): self._obs = obs
    def list(self, type_=None, subject=None): return list(self._obs)

class FakeClusterer(Clusterer):
    def __init__(self, clusters): self._c = clusters
    def cluster(self, observations, existing): return list(self._c)

class FakeDrafter(Drafter):
    def __init__(self, consolidates=True): self._ok = consolidates
    def draft(self, cluster, scope):
        return PromotionDraft(title=cluster.concept, statement="cohesive " + cluster.concept,
                              consolidates=self._ok, justification="j")

def _obs(subject, name):
    return MemoryObservation(type="feedback", subject=subject, name=name, description="d")

def _vault(tmp_path):
    (tmp_path / "10-projects" / "LOGOS").mkdir(parents=True)
    (tmp_path / "10-projects" / "agent-swarm").mkdir(parents=True)
    return tmp_path

def _run(vault, obs, clusters, drafter=None):
    return run_synthesis(
        reader=FakeReader(obs),
        writer=VaultWriteProvider(vault_path=vault),
        store=PromotionStore(vault),
        clusterer=FakeClusterer(clusters),
        drafter=drafter or FakeDrafter(),
        vault_path=vault,
        today=date(2026, 8, 15),
    )

def test_promotes_cross_boundary_cluster(tmp_path):
    v = _vault(tmp_path)
    obs = [_obs("LOGOS", "l1"), _obs("agent-swarm", "a1")]
    clusters = [Cluster("verify-before-claiming", obs)]
    res = _run(v, obs, clusters)
    assert res.written == ["verify-before-claiming"]
    # sibling projects -> common prefix 10-projects
    assert (v / "10-projects/promotions/verify-before-claiming.md").is_file()

def test_skips_single_scope_cluster(tmp_path):
    v = _vault(tmp_path)
    obs = [_obs("LOGOS", "l1"), _obs("LOGOS", "l2")]
    res = _run(v, obs, [Cluster("local-thing", obs)])
    assert res.written == []
    assert "local-thing" in res.skipped

def test_skips_when_drafter_says_no_consolidation(tmp_path):
    v = _vault(tmp_path)
    obs = [_obs("LOGOS", "l1"), _obs("agent-swarm", "a1")]
    res = _run(v, obs, [Cluster("restate", obs)], drafter=FakeDrafter(consolidates=False))
    assert res.written == []

def test_second_run_is_noop_convergence(tmp_path):
    v = _vault(tmp_path)
    obs = [_obs("LOGOS", "l1"), _obs("agent-swarm", "a1")]
    clusters = [Cluster("verify-before-claiming", obs)]
    _run(v, obs, clusters)
    res2 = _run(v, obs, clusters)          # identical corpus + clusters
    assert res2.written == []              # nothing re-minted

def test_grown_cluster_does_not_proliferate(tmp_path):
    v = _vault(tmp_path)
    obs1 = [_obs("LOGOS", "l1"), _obs("agent-swarm", "a1")]
    _run(v, obs1, [Cluster("verify-before-claiming", obs1)])
    grown = obs1 + [_obs("user", "u1")]
    res2 = _run(v, grown, [Cluster("verify-before-claiming", grown)])
    assert res2.written == []              # existing sources subset of grown -> covered, no duplicate

def test_memory_is_never_written(tmp_path):
    # the pass only writes under promotions/; assert no .memory path is touched
    v = _vault(tmp_path)
    obs = [_obs("LOGOS", "l1"), _obs("agent-swarm", "a1")]
    _run(v, obs, [Cluster("c", obs)])
    assert not list(v.rglob(".memory/*"))

def test_two_nested_clusters_in_one_pass_no_double_write(tmp_path):
    v = _vault(tmp_path)
    obs = [_obs("LOGOS", "l1"), _obs("agent-swarm", "a1")]
    grown = obs + [_obs("user", "u1")]
    res = _run(v, grown, [Cluster("dup-concept", obs), Cluster("dup-concept", grown)])
    assert res.written == ["dup-concept"]


class _ExplodingDrafter(Drafter):
    def draft(self, cluster, scope):
        if cluster.concept == "boom":
            raise RuntimeError("draft failed")
        return PromotionDraft(title=cluster.concept, statement="s", consolidates=True, justification="j")


def test_pass_continues_when_a_cluster_errors(tmp_path):
    v = _vault(tmp_path)
    ok = [_obs("LOGOS", "o1"), _obs("agent-swarm", "o2")]
    boom = [_obs("LOGOS", "x1"), _obs("agent-swarm", "x2")]
    res = run_synthesis(
        reader=FakeReader(ok + boom), writer=VaultWriteProvider(vault_path=v),
        store=PromotionStore(v), clusterer=FakeClusterer([Cluster("boom", boom), Cluster("good", ok)]),
        drafter=_ExplodingDrafter(), vault_path=v, today=date(2026, 8, 15))
    assert "boom" in res.skipped
    assert res.written == ["good"]


def test_pid_collision_disambiguated_no_overwrite(tmp_path):
    # two DISTINCT concepts (non-nested member sets) slugging to the same pid must
    # NOT overwrite each other -> both written with distinct ids, both files on disk
    v = _vault(tmp_path)
    obs1 = [_obs("LOGOS", "a1"), _obs("agent-swarm", "a2")]
    obs2 = [_obs("LOGOS", "b1"), _obs("agent-swarm", "b2")]
    res = _run(v, obs1 + obs2, [Cluster("Foo Bar", obs1), Cluster("Foo-Bar", obs2)])
    assert len(res.written) == 2 and len(set(res.written)) == 2
    assert len(list(v.rglob("promotions/*.md"))) == 2
