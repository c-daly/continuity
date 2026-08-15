import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from memory_read_provider import MemoryObservation
from llm_synthesis import LLMClusterer, LLMDrafter
from promotion import Cluster


class FakeRunner:
    def __init__(self, payload): self._payload = payload
    def complete(self, prompt): return self._payload

def _obs(subject, name):
    return MemoryObservation(type="feedback", subject=subject, name=name, description="d-" + name)

def test_clusterer_maps_json_to_clusters():
    obs = [_obs("LOGOS", "l1"), _obs("agent-swarm", "a1"), _obs("user", "u1")]
    payload = json.dumps({"clusters": [
        {"concept": "verify before claiming", "members": ["l1", "a1"]}]})
    clusters = LLMClusterer(FakeRunner(payload)).cluster(obs, [])
    assert len(clusters) == 1
    assert clusters[0].concept == "verify before claiming"
    assert {m.name for m in clusters[0].members} == {"l1", "a1"}

def test_clusterer_drops_unknown_member_names():
    obs = [_obs("LOGOS", "l1")]
    payload = json.dumps({"clusters": [{"concept": "c", "members": ["l1", "ghost"]}]})
    clusters = LLMClusterer(FakeRunner(payload)).cluster(obs, [])
    assert {m.name for m in clusters[0].members} == {"l1"}

def test_clusterer_tolerates_garbage_json():
    assert LLMClusterer(FakeRunner("not json")).cluster([_obs("a", "x")], []) == []

def test_drafter_maps_json_to_draft():
    payload = json.dumps({"title": "Verify First", "statement": "S",
                          "consolidates": True, "justification": "j"})
    d = LLMDrafter(FakeRunner(payload)).draft(Cluster("c", [_obs("a", "x")]), "10-projects")
    assert d.title == "Verify First" and d.consolidates is True
