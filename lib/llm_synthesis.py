"""LLM-backed clusterer + drafter, behind the promotion.Clusterer/Drafter ABCs.

The only external coupling is ClaudeCliRunner (subprocess `claude -p`). All
parsing is deterministic and unit-tested with a fake runner.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional, Protocol

sys.path.insert(0, str(Path(__file__).parent))
from memory_read_provider import MemoryObservation  # noqa: E402
from promotion import Cluster, PromotionDraft, Clusterer, Drafter  # noqa: E402


class LLMRunner(Protocol):
    def complete(self, prompt: str) -> str: ...


class ClaudeCliRunner:
    def __init__(self, model: Optional[str] = None, timeout: int = 120):
        self.model = model
        self.timeout = timeout

    def complete(self, prompt: str) -> str:
        cmd = ["claude", "-p", prompt]
        if self.model:
            cmd += ["--model", self.model]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"claude -p failed ({proc.returncode}): {proc.stderr.strip()}")
        return proc.stdout


def _obs_line(o: MemoryObservation) -> str:
    return f"- name={o.name} | scope={o.subject} | type={o.type} | {o.description}"


class LLMClusterer(Clusterer):
    def __init__(self, runner: LLMRunner):
        self.runner = runner

    def cluster(self, observations, existing) -> list[Cluster]:
        by_name = {o.name: o for o in observations}
        prompt = _CLUSTER_PROMPT.format(
            entries="\n".join(_obs_line(o) for o in observations),
            existing="\n".join(f"- {p.title}" for p in existing) or "(none)",
        )
        try:
            data = json.loads(self.runner.complete(prompt))
            out = []
            for c in data.get("clusters", []) or []:
                members = [by_name[n] for n in (c.get("members", []) or []) if n in by_name]
                if members:
                    out.append(Cluster(concept=str(c.get("concept", "")).strip(), members=members))
            return out
        except (ValueError, RuntimeError, AttributeError, TypeError):
            return []


class LLMDrafter(Drafter):
    def __init__(self, runner: LLMRunner):
        self.runner = runner

    def draft(self, cluster: Cluster, scope: str) -> PromotionDraft:
        prompt = _DRAFT_PROMPT.format(
            concept=cluster.concept, scope=scope or "(vault root / user)",
            members="\n".join(_obs_line(o) for o in cluster.members),
        )
        try:
            data = json.loads(self.runner.complete(prompt))
            return PromotionDraft(
                title=str(data.get("title", cluster.concept)).strip(),
                statement=str(data.get("statement", "")).strip(),
                consolidates=bool(data.get("consolidates", False)),
                justification=str(data.get("justification", "")).strip(),
            )
        except (ValueError, RuntimeError, AttributeError, TypeError):
            return PromotionDraft(title=cluster.concept, statement="", consolidates=False,
                                  justification="draft failed")


_CLUSTER_PROMPT = """You are continuity's synthesis step. Below are first-order memory
entries from across many projects. Identify concepts that RECUR across two or more
distinct scopes (the `scope=` field). Return ONLY JSON:
{{"clusters":[{{"concept":"<short name>","members":["<name>","<name>"]}}]}}
Only group entries that express the SAME underlying idea. Ignore single-scope repeats.
Existing promotions (do not recreate these):
{existing}

Entries:
{entries}
"""

_DRAFT_PROMPT = """Consolidate these recurring memory entries about "{concept}" (scope: {scope})
into one cohesive statement. Return ONLY JSON:
{{"title":"<short>","statement":"<the refined cohesive idea>","consolidates":<true|false>,"justification":"<one line>"}}
Set consolidates=false if these do not actually share one idea (a mere restatement).

Entries:
{members}
"""
