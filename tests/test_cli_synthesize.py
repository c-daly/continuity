import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from memory_read_provider import MemoryObservation
from promotion import Cluster, PromotionDraft, Clusterer, Drafter, PromotionStore
from vault_write_provider import VaultWriteProvider
import cli


class _Reader:
    def __init__(self, o):
        self._o = o

    def list(self, type_=None, subject=None):
        return list(self._o)


class _Clusterer(Clusterer):
    def __init__(self, c):
        self._c = c

    def cluster(self, obs, existing):
        return list(self._c)


class _Drafter(Drafter):
    def draft(self, cluster, scope):
        return PromotionDraft(cluster.concept, "s", True, "j")


def test_cmd_synthesize_writes_and_reports(tmp_path, capsys):
    (tmp_path / "10-projects" / "LOGOS").mkdir(parents=True)
    (tmp_path / "10-projects" / "agent-swarm").mkdir(parents=True)
    obs = [MemoryObservation("feedback", "LOGOS", "l1", "d"),
           MemoryObservation("feedback", "agent-swarm", "a1", "d")]
    deps = dict(reader=_Reader(obs), writer=VaultWriteProvider(vault_path=tmp_path),
                store=PromotionStore(tmp_path), clusterer=_Clusterer([Cluster("cross", obs)]),
                drafter=_Drafter(), vault_path=tmp_path, today=date(2026, 8, 15))
    rc = cli.cmd_synthesize([], deps=deps)
    assert rc == 0
    assert "written 1" in capsys.readouterr().out
    assert (tmp_path / "10-projects/promotions/cross.md").is_file()
