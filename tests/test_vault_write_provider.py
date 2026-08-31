"""Tests for VaultWriteProvider."""

import pytest
import yaml

from vault_write_provider import VaultWriteProvider


# --- construction ---


def test_explicit_vault_path(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    assert wp.vault_path == fake_vault


def test_env_var_fallback(fake_vault, monkeypatch):
    monkeypatch.setenv("CONTINUITY_VAULT_DIR", str(fake_vault))
    wp = VaultWriteProvider()
    assert wp.vault_path == fake_vault


def test_no_vault_path_raises(monkeypatch):
    monkeypatch.delenv("CONTINUITY_VAULT_DIR", raising=False)
    monkeypatch.delenv("VAULT_DIR", raising=False)
    with pytest.raises(ValueError, match="Vault path not provided"):
        VaultWriteProvider()


def test_nonexistent_vault_raises(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        VaultWriteProvider(vault_path=tmp_path / "no-such-dir")


# --- write: path mapping ---


def test_write_insight_path(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    wp.write(
        kind="cont.insight",
        id="2026-05-09-foo",
        frontmatter={"date": "2026-05-09", "project": "test-project"},
        body="Hello.",
    )
    expected = (
        fake_vault / "10-projects" / "test-project" / "insights" / "2026-05-09-foo.md"
    )
    assert expected.is_file()


def test_write_decision_path(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    wp.write(
        kind="cont.decision",
        id="2026-05-09-bar",
        frontmatter={"date": "2026-05-09", "project": "test-project"},
        body="Decision body.",
    )
    expected = (
        fake_vault / "10-projects" / "test-project" / "decisions" / "2026-05-09-bar.md"
    )
    assert expected.is_file()


def test_write_creates_parent_dirs(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    wp.write(
        kind="cont.insight",
        id="x",
        frontmatter={"project": "brand-new-project"},
        body="b",
    )
    target = fake_vault / "10-projects" / "brand-new-project" / "insights" / "x.md"
    assert target.is_file()


# --- write: rendering ---


def test_write_frontmatter_shape(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    wp.write(
        kind="cont.insight",
        id="i1",
        frontmatter={"date": "2026-05-09", "project": "test-project", "type": "insight"},
        body="Body text.",
    )
    target = fake_vault / "10-projects" / "test-project" / "insights" / "i1.md"
    text = target.read_text()
    assert text.startswith("---\n")
    head, _, body_part = text.partition("\n---\n")
    parsed = yaml.safe_load(head[len("---\n"):])
    assert parsed == {
        "date": "2026-05-09",
        "project": "test-project",
        "type": "insight",
    }
    assert "Body text." in body_part
    assert text.endswith("\n")


def test_write_preserves_key_order(fake_vault):
    """Frontmatter key order in the file matches insertion order."""
    wp = VaultWriteProvider(vault_path=fake_vault)
    wp.write(
        kind="cont.insight",
        id="ordered",
        frontmatter={"z_last": 1, "a_first": 2, "project": "test-project"},
        body="b",
    )
    target = fake_vault / "10-projects" / "test-project" / "insights" / "ordered.md"
    text = target.read_text()
    head = text.split("\n---\n", 1)[0]
    keys_in_order = [
        line.split(":", 1)[0]
        for line in head.splitlines()
        if line and not line.startswith("---")
    ]
    assert keys_in_order == ["z_last", "a_first", "project"]


# --- write: idempotency / overwrite ---


def test_write_is_idempotent_for_same_input(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    fm = {"project": "test-project", "v": 1}
    wp.write("cont.insight", "same", fm, "body")
    target = fake_vault / "10-projects" / "test-project" / "insights" / "same.md"
    first = target.read_text()
    wp.write("cont.insight", "same", fm, "body")
    assert target.read_text() == first


def test_write_overwrites_with_new_content(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    wp.write("cont.insight", "ow", {"project": "test-project"}, "first")
    wp.write("cont.insight", "ow", {"project": "test-project"}, "second")
    target = fake_vault / "10-projects" / "test-project" / "insights" / "ow.md"
    assert "second" in target.read_text()
    assert "first" not in target.read_text()


def test_write_no_temp_file_remains(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    wp.write("cont.insight", "tmp-check", {"project": "test-project"}, "x")
    parent = fake_vault / "10-projects" / "test-project" / "insights"
    leftovers = [p.name for p in parent.iterdir() if p.name.startswith(".")]
    assert leftovers == []


# --- write: error paths ---


def test_write_unknown_kind_raises(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    with pytest.raises(ValueError, match="Unknown kind"):
        wp.write("cont.bogus", "x", {"project": "p"}, "b")


def test_write_missing_project_raises(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    with pytest.raises(ValueError, match="project"):
        wp.write("cont.insight", "x", {}, "b")


# --- exists ---


def test_exists_false_when_absent(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    assert wp.exists("cont.insight", "nope") is False


def test_exists_true_after_write(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    wp.write("cont.insight", "yep", {"project": "test-project"}, "b")
    assert wp.exists("cont.insight", "yep") is True


def test_exists_finds_across_projects(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    wp.write("cont.insight", "shared", {"project": "test-project"}, "b")
    # exists() searches all project subtrees
    assert wp.exists("cont.insight", "shared") is True


def test_exists_unknown_kind_raises(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    with pytest.raises(ValueError, match="Unknown kind"):
        wp.exists("cont.bogus", "x")


def test_exists_no_projects_root(tmp_path):
    """Vault without 10-projects/ returns False rather than crashing."""
    wp = VaultWriteProvider(vault_path=tmp_path)
    assert wp.exists("cont.insight", "x") is False


# --- path traversal rejection ---


@pytest.mark.parametrize(
    "bad_project",
    ["..", "../escape", "/abs/path", ".", "", "LOGOS/../../etc", "a//b"],
)
def test_write_rejects_traversal_in_project(fake_vault, bad_project):
    """`nested/path` is deliberately absent: a project may be nested now, so the
    check validates each segment rather than forbidding the separator. Every
    form that could still climb out of the vault is here."""
    wp = VaultWriteProvider(vault_path=fake_vault)
    with pytest.raises(ValueError):
        wp.write("cont.insight", "ok", {"project": bad_project}, "b")


@pytest.mark.parametrize(
    "bad_id",
    ["..", "../escape", "/abs/path", "nested/path", "."],
)
def test_write_rejects_traversal_in_id(fake_vault, bad_id):
    wp = VaultWriteProvider(vault_path=fake_vault)
    with pytest.raises(ValueError):
        wp.write("cont.insight", bad_id, {"project": "test-project"}, "b")


def test_exists_rejects_traversal_in_id(fake_vault):
    wp = VaultWriteProvider(vault_path=fake_vault)
    with pytest.raises(ValueError):
        wp.exists("cont.insight", "../escape")


def test_write_does_not_escape_vault_root(fake_vault, tmp_path):
    """Confirm that traversal would have escaped without the validation."""
    wp = VaultWriteProvider(vault_path=fake_vault)
    sentinel_outside = tmp_path / "outside.md"
    # Without validation, project='..' under '10-projects' would resolve
    # into tmp_path. Confirm it raises rather than writing there.
    with pytest.raises(ValueError):
        wp.write("cont.insight", "outside", {"project": ".."}, "x")
    assert not sentinel_outside.exists()

# --- promotions (scope-driven) ---


def test_promotion_writes_at_project_scope(fake_vault):
    (fake_vault / "10-projects" / "LOGOS").mkdir(parents=True)
    w = VaultWriteProvider(vault_path=fake_vault)
    w.write(
        "cont.promotion",
        "concept-x",
        {"scope": "10-projects/LOGOS", "kind": "promotion"},
        "body",
    )
    assert (fake_vault / "10-projects/LOGOS/promotions/concept-x.md").is_file()


def test_promotion_writes_at_root_scope(fake_vault):
    w = VaultWriteProvider(vault_path=fake_vault)
    w.write(
        "cont.promotion",
        "concept-y",
        {"scope": "", "kind": "promotion"},
        "body",
    )
    assert (fake_vault / "promotions/concept-y.md").is_file()


def test_promotion_creates_missing_scope_dirs(fake_vault):
    w = VaultWriteProvider(vault_path=fake_vault)
    w.write(
        "cont.promotion",
        "z",
        {"scope": "10-projects/New", "kind": "promotion"},
        "b",
    )
    assert (fake_vault / "10-projects/New/promotions/z.md").is_file()


def test_promotion_rejects_traversal_scope(fake_vault):
    w = VaultWriteProvider(vault_path=fake_vault)
    with pytest.raises(ValueError):
        w.write(
            "cont.promotion",
            "z",
            {"scope": "../evil", "kind": "promotion"},
            "b",
        )


def test_promotion_rejects_traversal_id(fake_vault):
    w = VaultWriteProvider(vault_path=fake_vault)
    with pytest.raises(ValueError):
        w.write(
            "cont.promotion",
            "../evil",
            {"scope": "", "kind": "promotion"},
            "b",
        )

def test_exists_promotion_id_matches_literally_not_as_glob(fake_vault):
    (fake_vault).mkdir(parents=True, exist_ok=True)
    w = VaultWriteProvider(vault_path=fake_vault)
    w.write("cont.promotion", "aXb", {"scope": "", "kind": "promotion"}, "b")
    assert w.exists("cont.promotion", "aXb") is True
    assert w.exists("cont.promotion", "a*b") is False   # "*" must not glob-match aXb



# --- nested sub-projects ---

def _nested(vault):
    sub = vault / "10-projects" / "LOGOS" / "apollo"
    sub.mkdir(parents=True)
    (sub / "narrative.md").write_text("# apollo\n")
    (vault / "10-projects" / "LOGOS" / "narrative.md").write_text("# LOGOS\n")
    return vault


def test_write_places_an_insight_in_a_nested_subproject(tmp_path):
    """The bug: 'apollo' resolved to a flat 10-projects/apollo/ that nothing
    has, so the insight and the narrative naming it lived in different trees."""
    vault = _nested(tmp_path)
    VaultWriteProvider(vault_path=vault).write(
        "cont.insight", "2026-08-31-x", {"project": "apollo"}, "body"
    )

    assert (vault / "10-projects/LOGOS/apollo/insights/2026-08-31-x.md").is_file()
    assert not (vault / "10-projects/apollo").exists()


def test_write_accepts_an_explicit_nested_path(tmp_path):
    vault = _nested(tmp_path)
    VaultWriteProvider(vault_path=vault).write(
        "cont.insight", "2026-08-31-y", {"project": "LOGOS/apollo"}, "body"
    )

    assert (vault / "10-projects/LOGOS/apollo/insights/2026-08-31-y.md").is_file()


def test_write_still_creates_an_unknown_top_level_project(tmp_path):
    """Writing to a name the vault has never seen is how a new project starts."""
    vault = _nested(tmp_path)
    VaultWriteProvider(vault_path=vault).write(
        "cont.insight", "2026-08-31-z", {"project": "brand-new"}, "body"
    )

    assert (vault / "10-projects/brand-new/insights/2026-08-31-z.md").is_file()


def test_write_still_refuses_to_escape_the_vault(tmp_path):
    vault = _nested(tmp_path)
    wp = VaultWriteProvider(vault_path=vault)
    for hostile in ("../../etc", "/etc", "LOGOS/../../../etc", ".."):
        with pytest.raises(ValueError):
            wp.write("cont.insight", "id", {"project": hostile}, "body")


def test_write_refuses_an_unregistered_nested_path(tmp_path):
    """Resolution rejecting `LOGOS/decisions` is not enough on its own — the
    create-a-new-project fallback would take the unresolved path and write there
    anyway, straight into another project's decisions tree.

    The asymmetry is deliberate. A top-level project's identity IS its directory
    under 10-projects/, so writing a new name creates it. A nested project needs
    a narrative to tell it from an artifact directory, so it must exist first."""
    vault = _nested(tmp_path)
    (vault / "10-projects" / "LOGOS" / "decisions").mkdir()
    wp = VaultWriteProvider(vault_path=vault)

    with pytest.raises(ValueError, match="not a known project"):
        wp.write("cont.insight", "id", {"project": "LOGOS/decisions"}, "b")
    assert not (vault / "10-projects/LOGOS/decisions/insights").exists()


def test_write_refuses_to_invent_a_nested_project(tmp_path):
    vault = _nested(tmp_path)
    wp = VaultWriteProvider(vault_path=vault)

    with pytest.raises(ValueError, match="not a known project"):
        wp.write("cont.insight", "id", {"project": "LOGOS/brand-new"}, "b")
