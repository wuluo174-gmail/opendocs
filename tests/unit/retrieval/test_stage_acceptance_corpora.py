"""Unit tests for stage-owned S4 acceptance corpus owners."""

from __future__ import annotations

from opendocs.retrieval.stage_acceptance_corpora import (
    load_s4_acceptance_corpora,
    materialize_s4_tc005_acceptance_corpus,
    resolve_s4_tc018_corpus_dir,
)


class TestStageAcceptanceCorpora:
    def test_tc005_generated_corpus_uses_stage_manifest_label(self, tmp_path) -> None:
        corpora = load_s4_acceptance_corpora()
        corpus_dir, manifest_label = materialize_s4_tc005_acceptance_corpus(tmp_path / "corpus")
        assert corpora.tc005.mode == "generated"
        assert manifest_label == corpora.tc005.manifest_label
        assert (corpus_dir / "zh_project_plan.md").is_file()

    def test_tc018_fixture_corpus_resolves_required_documents(self) -> None:
        corpora = load_s4_acceptance_corpora()
        corpus_dir = resolve_s4_tc018_corpus_dir()
        assert corpora.tc018.mode == "fixture"
        assert corpus_dir.is_dir()
        for name in corpora.tc018.required_documents:
            assert (corpus_dir / name).is_file()
