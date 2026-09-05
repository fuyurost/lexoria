"""Daily-sheet rendering and PDF storage (self-contained, no ORM imports).

Single source of truth for the printable artifact:

* ``render_html`` renders the SAME Jinja document used by both the preview
  endpoint (frontends embed it as-is) and the PDF generator. Autoescaping is
  always on, so user-authored text (lemma / phonetic / definitions) can never
  inject markup into the preview.
* ``render_pdf_bytes`` shells out to WeasyPrint. WeasyPrint is imported
  lazily on purpose: a minimal dev/test environment may not have it, but
  production generation NEVER falls back to a non-PDF artifact — callers get
  :class:`PdfUnavailableError` / :class:`PdfRenderError` instead.
* ``store_pdf_bytes`` writes to a temp file inside the storage directory,
  ``flush`` + ``fsync`` it, then atomically ``os.replace`` to a random
  internal key (never user-suppliable).
* ``resolve_pdf_path`` resolves a stored key and refuses anything that
  escapes the storage directory (path-traversal / absolute / UNC).

The WeasyPrint ``url_fetcher`` is overridden to block EVERY resource fetch
(data:, file:, http(s):, ...): templates are fully inline (no images, no
external fonts, no @font-face URLs), so a fetch is always a bug or an
attack — never a working feature.
"""
from __future__ import annotations

import os
import secrets
import tempfile
from functools import lru_cache
from pathlib import Path

import jinja2

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates" / "daily"

# Snapshot content keys persisted to DailySheetItem.content_snapshot. No
# rendering fingerprint (html/css) is ever stored: the sheet is re-rendered
# from these fields whenever needed.
SNAPSHOT_KEYS = (
    "lemma",
    "normalized_lemma",
    "personal_phonetic",
    "senses",
    "item_type",
    "selection_reason",
)
SENSE_KEYS = ("part_of_speech", "definition_zh", "definition_en")
MAX_SENSES = 2  # snapshot & templates show at most the two first senses

_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
    trim_blocks=True,
    lstrip_blocks=True,
    auto_reload=False,
)


class PdfUnavailableError(RuntimeError):
    """WeasyPrint is not importable in this environment."""


class PdfRenderError(RuntimeError):
    """WeasyPrint failed to turn the HTML into PDF bytes."""


class PdfStorageError(RuntimeError):
    """Storage directory unusable or file write failed."""


class PdfResourceBlocked(RuntimeError):
    """The strict url_fetcher rejected a resource reference."""


# --- exceptions -> API errors (raised by the caller) ----------------------


def pdf_unavailable_error() -> Exception:
    from app.core.errors import AppError

    return AppError(
        500,
        "pdf_renderer_unavailable",
        "PDF 渲染组件不可用（WeasyPrint 未安装）",
    )


def pdf_render_error(detail: str) -> Exception:
    from app.core.errors import AppError

    return AppError(
        500,
        "pdf_render_failed",
        "PDF 渲染失败",
        details={"reason": detail},
    )


def pdf_storage_error(detail: str) -> Exception:
    from app.core.errors import AppError

    return AppError(
        500,
        "pdf_storage_failed",
        "PDF 存储失败",
        details={"reason": detail},
    )


# --- stylesheet ------------------------------------------------------------


@lru_cache(maxsize=1)
def _stylesheet() -> str:
    return (TEMPLATES_DIR / "daily.css").read_text(encoding="utf-8")


# --- content snapshots (pure) ----------------------------------------------


def build_snapshot(
    *,
    lemma: str,
    normalized_lemma: str,
    personal_phonetic: str | None,
    senses: list[dict] | tuple[dict, ...],
    item_type: str,
    selection_reason: str,
) -> dict:
    """Persistable snapshot dict for one sheet item (see SNAPSHOT_KEYS).

    ``senses`` must already be ordered (sort_order asc); the first
    ``MAX_SENSES`` entries are kept, each carrying exactly SENSE_KEYS.
    """
    kept = []
    for sense in senses[:MAX_SENSES]:
        kept.append({key: sense.get(key) for key in SENSE_KEYS})
    return {
        "lemma": lemma,
        "normalized_lemma": normalized_lemma,
        "personal_phonetic": personal_phonetic,
        "senses": kept,
        "item_type": item_type,
        "selection_reason": selection_reason,
    }


# --- HTML (shared by preview + PDF) -----------------------------------------


def _html_row(row: dict) -> dict:
    """Selection row (dict built by the API layer) -> template context row."""
    senses = row.get("senses") or []
    return {
        "no": row["sort_order"],
        "lemma": row["lemma"],
        "phonetic": row.get("personal_phonetic") or "",
        "senses": [dict(s) for s in senses[:MAX_SENSES]],
        "item_type": row["item_type"],
        "reason": row["selection_reason"],
        "is_new": row["item_type"] == "new",
        "is_hard": row["selection_reason"] == "recent_hard",
    }


def render_html(
    *,
    template: str,  # "compact" | "test"
    paper_size: str,  # "a4" | "a5"
    columns: int,  # 1 | 2
    sheet_date: str,  # ISO date (user-local day)
    rows: list[dict],
    review_count: int,
    new_count: int,
) -> str:
    """Full standalone HTML document for one daily sheet (escaped content).

    Both endpoints share this function so the preview HTML is byte-identical
    to what WeasyPrint renders for the generated PDF.
    """
    context_rows = [_html_row(row) for row in rows]
    ctx = {
        "template": template,
        "paper_size": paper_size,
        "columns": int(columns),
        "sheet_date": sheet_date,
        "rows": context_rows,
        "hard_rows": [r for r in context_rows if r["is_hard"]],
        "review_count": int(review_count),
        "new_count": int(new_count),
        "stylesheet": _stylesheet(),
    }
    tpl = _ENV.get_template(f"{template}.html")
    return tpl.render(ctx)


# --- WeasyPrint --------------------------------------------------------------


def _blocking_url_fetcher(url: str, *args, **kwargs) -> None:
    """Reject every resource fetch; the sheets are fully inline documents."""
    raise PdfResourceBlocked(f"external resource blocked: {url[:80]!r}")


def weasyprint_available() -> bool:
    try:
        import weasyprint  # noqa: F401

        return True
    except Exception:  # noqa: BLE001 - ImportError / missing native libs
        return False


def render_pdf_bytes(html: str) -> bytes:
    """Render the (already-escaped) sheet HTML to PDF bytes via WeasyPrint."""
    try:
        from weasyprint import HTML
    except Exception as exc:
        raise PdfUnavailableError(str(exc)) from exc
    try:
        return HTML(string=html, base_url=None, url_fetcher=_blocking_url_fetcher).write_pdf()
    except PdfResourceBlocked:
        raise
    except Exception as exc:
        raise PdfRenderError(str(exc)) from exc


# --- PDF storage --------------------------------------------------------------


def _storage_dir(directory: str | Path) -> Path:
    path = Path(directory)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PdfStorageError(str(exc)) from exc
    return path


def store_pdf_bytes(data: bytes, directory: str | Path) -> str:
    """Atomically persist PDF bytes inside ``directory``; returns the random
    internal storage key (bare filename, never caller-controlled)."""
    folder = _storage_dir(directory)
    key = f"{secrets.token_urlsafe(18)}.pdf"
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=".sheet-", suffix=".tmp", dir=folder)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, folder / key)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
    except PdfStorageError:
        raise
    except OSError as exc:
        raise PdfStorageError(str(exc)) from exc
    return key


def resolve_pdf_path(directory: str | Path, key: str | None) -> Path | None:
    """Safe path for a stored PDF, or None when missing/unsafe/not a file.

    The resolved candidate MUST stay inside the storage directory (guards
    traversal and absolute keys); symlink escape is impossible because the
    directory holds only files this service wrote.
    """
    if not key:
        return None
    folder = Path(directory).resolve()
    candidate = (folder / key).resolve()
    try:
        candidate.relative_to(folder)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


def delete_pdf(directory: str | Path, key: str) -> None:
    """Best-effort removal of a stored PDF (used on DB write failure)."""
    path = resolve_pdf_path(directory, key)
    if path is not None:
        try:
            path.unlink()
        except OSError:
            pass
