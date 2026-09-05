"""Unit tests for daily-sheet rendering (app/services/pdf.py).

Pure: no database, no network. HTML/escaping/template-parameter behaviour is
verified here; WeasyPrint round-trips run only when the library is actually
importable in the current environment (never required for the suite).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.services import pdf as pdf_service
from app.services.pdf import (
    PdfResourceBlocked,
    build_snapshot,
    render_html,
    resolve_pdf_path,
    store_pdf_bytes,
)

SHEET_DATE = "2026-09-05"


def row(
    lemma: str = "apple",
    *,
    phonetic: str | None = "/ˈæp.əl/",
    senses: list[dict] | None = None,
    item_type: str = "review",
    reason: str = "due_today",
    sort_order: int = 1,
) -> dict:
    return {
        "sort_order": sort_order,
        "lemma": lemma,
        "normalized_lemma": lemma.casefold(),
        "personal_phonetic": phonetic,
        "senses": senses if senses is not None else [],
        "item_type": item_type,
        "selection_reason": reason,
        "user_word_id": sort_order,
        "review_card_id": None,
    }


def sense(pos: str | None = None, zh: str | None = None, en: str | None = None) -> dict:
    return {"part_of_speech": pos, "definition_zh": zh, "definition_en": en}


def html(
    rows: list[dict],
    *,
    template: str = "compact",
    paper_size: str = "a4",
    columns: int = 1,
    review_count: int | None = None,
    new_count: int | None = None,
) -> str:
    counts = {"review": 0, "new": 0}
    for r in rows:
        counts[r["item_type"]] += 1
    return render_html(
        template=template,
        paper_size=paper_size,
        columns=columns,
        sheet_date=SHEET_DATE,
        rows=rows,
        review_count=counts["review"] if review_count is None else review_count,
        new_count=counts["new"] if new_count is None else new_count,
    )


# --- snapshot content --------------------------------------------------------


def test_snapshot_contains_only_contract_fields():
    snap = build_snapshot(
        lemma="apple",
        normalized_lemma="apple",
        personal_phonetic="/ˈæp.əl/",
        senses=[sense("n.", "苹果", "fruit")],
        item_type="review",
        selection_reason="due_today",
    )
    # Every required field, nothing extra (no rendering fingerprint like html).
    assert set(snap) == {
        "lemma",
        "normalized_lemma",
        "personal_phonetic",
        "senses",
        "item_type",
        "selection_reason",
    }
    assert set(snap["senses"][0]) == {
        "part_of_speech",
        "definition_zh",
        "definition_en",
    }


def test_snapshot_slices_to_two_senses_and_copies():
    senses = [
        sense("n.", "义一", "one"),
        sense("v.", "义二", "two"),
        sense("adj.", "义三", "three"),
    ]
    snap = build_snapshot(
        lemma="run",
        normalized_lemma="run",
        personal_phonetic=None,
        senses=senses,
        item_type="new",
        selection_reason="new",
    )
    assert [s["definition_zh"] for s in snap["senses"]] == ["义一", "义二"]
    assert len(snap["senses"]) == 2
    # Snapshot is decoupled from the caller's list.
    senses[0]["definition_zh"] = "mutated"
    assert snap["senses"][0]["definition_zh"] == "义一"


# --- escaping ----------------------------------------------------------------


def test_compact_html_escapes_user_content():
    rows = [
        row(
            '<img src=x onerror="alert(1)">',
            phonetic='"><script>bad()</script>',
            senses=[sense("n.", "<b>苹果</b> & more", "fruit 'quoted'")],
        )
    ]
    out = html(rows)
    assert "<script>" not in out
    assert "<img" not in out
    assert "<b>苹果</b>" not in out
    assert "&lt;script&gt;" in out
    assert "&lt;img src=x onerror=" in out
    assert "&lt;b&gt;苹果&lt;/b&gt;" in out


def test_hard_words_footer_escapes_lemma():
    rows = [row('a<&>b"', phonetic=None, reason="recent_hard")]
    out = html(rows)
    assert "a&lt;&amp;&gt;b&#34;" in out  # escaped in the footer recap


def test_preview_document_is_single_self_contained_file():
    out = html([row()])
    # No external resource ever referenced: nothing to fetch for WeasyPrint.
    for needle in ("src=", "href=", "@font-face", "url("):
        assert needle not in out


# --- template parameters -----------------------------------------------------


def test_paper_size_drives_page_rule():
    a4 = html([row()], paper_size="a4")
    a5 = html([row()], paper_size="a5")
    assert "@page { size: A4" in a4
    assert "size: A5" not in a4
    assert "@page { size: A5" in a5
    assert "size: A4" not in a5


def test_columns_switch_body_class():
    assert 'class="paper-a4 cols-1"' in html([row()], columns=1)
    assert 'class="paper-a4 cols-2"' in html([row()], columns=2)


def test_header_shows_date_and_actual_counts():
    out = html([row(sort_order=1), row("new1", item_type="new", sort_order=2)])
    assert SHEET_DATE in out
    assert "复习 <b>1</b>" in out
    assert "新词 <b>1</b>" in out


def test_compact_renders_lemma_phonetic_and_two_senses_only():
    rows = [
        row(
            senses=[
                sense("n.", "义一", "one"),
                sense("v.", "义二", "two"),
                sense("adj.", "THIRD-SENSE-SHOULD-NOT-APPEAR", "three"),
            ]
        )
    ]
    out = html(rows)
    assert "apple" in out
    assert "/ˈæp.əl/" in out
    assert "义一" in out
    assert "义二" in out
    assert "THIRD-SENSE-SHOULD-NOT-APPEAR" not in out
    assert 'class="box"' in out  # per-row review checkbox


def test_compact_marks_new_rows():
    out = html([row("fresh", item_type="new", reason="new")])
    assert "is-new" in out


def test_test_template_hides_definitions_and_has_writing_line():
    rows = [
        row(
            phonetic="/ˈæp.əl/",
            senses=[sense("n.", "SECRET-DEFINITION-ZH", "SECRET-DEFINITION-EN")],
        )
    ]
    out = html(rows, template="test")
    assert "apple" in out
    assert "/ˈæp.əl/" in out
    assert 'class="write-line"' in out
    assert "SECRET-DEFINITION-ZH" not in out
    assert "SECRET-DEFINITION-EN" not in out


def test_test_template_renders_without_senses_at_all():
    out = html([row(senses=None)], template="test")
    assert "apple" in out
    assert "write-line" in out


# --- WeasyPrint round-trip (only when importable) ----------------------------

weasyprint_missing = not pdf_service.weasyprint_available()


@pytest.mark.skipif(weasyprint_missing, reason="WeasyPrint not importable")
@pytest.mark.parametrize("template", ["compact", "test"])
@pytest.mark.parametrize("paper_size", ["a4", "a5"])
@pytest.mark.parametrize("columns", [1, 2])
def test_real_pdf_generation(template, paper_size, columns):
    rows = [
        row("apple", senses=[sense("n.", "苹果", "fruit")]),
        row("学习", phonetic="/lɜːn/", item_type="new", reason="new",
            senses=[sense("v.", "学习", "to learn")], sort_order=2),
    ]
    doc = html(rows, template=template, paper_size=paper_size, columns=columns)
    data = pdf_service.render_pdf_bytes(doc)
    assert data[:4] == b"%PDF"
    assert len(data) > 1000


# --- strict url fetcher -------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://evil.example/x.png",
        "https://evil.example/x.png",
        "file:///etc/passwd",
        "data:text/html,<b>hi</b>",
        "//evil.example/x",
    ],
)
def test_url_fetcher_blocks_every_resource(url):
    with pytest.raises(PdfResourceBlocked):
        pdf_service._blocking_url_fetcher(url)


# --- storage path safety ------------------------------------------------------


def test_resolve_pdf_path_refuses_escapes(tmp_path: Path):
    (tmp_path / "ok.pdf").write_bytes(b"%PDF-1.4 ok")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "inner.pdf").write_bytes(b"%PDF-1.4 inner")
    resolved = resolve_pdf_path(tmp_path, "ok.pdf")
    assert resolved is not None and resolved.name == "ok.pdf"

    assert resolve_pdf_path(tmp_path, "sub/inner.pdf") is not None
    for bad in (
        "missing.pdf",
        "../evil.pdf",
        "..%2fevil.pdf",
        str((tmp_path.parent / "evil.pdf").resolve()),
        "ok.pdf/../evil.pdf",
        "",
        None,
    ):
        assert resolve_pdf_path(tmp_path, bad) is None, bad


def test_store_pdf_bytes_writes_atomic_file_with_random_key(tmp_path: Path):
    key1 = store_pdf_bytes(b"%PDF-1.4 first", tmp_path)
    key2 = store_pdf_bytes(b"%PDF-1.4 second", tmp_path)
    assert key1.endswith(".pdf") and key1 != key2
    assert (tmp_path / key1).read_bytes() == b"%PDF-1.4 first"
    assert (tmp_path / key2).read_bytes() == b"%PDF-1.4 second"
    # No leftover temp files after the atomic replaces.
    leftovers = [p for p in os.listdir(tmp_path) if p.startswith(".sheet-")]
    assert leftovers == []
    # Keys are opaque random names — never derivable from user input.
    assert set(key1) - set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.pdf") == set()
