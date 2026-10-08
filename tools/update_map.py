#!/usr/bin/env python3
"""Обновляет автоматические разделы КАРТА.md: реестр всех файлов и очередь upload/.

Ручные разделы карты (предметный указатель, каталог рисунков и т.п.) не трогает —
переписывается только текст между маркерами <!-- AUTO:... --> .

Код документа = первая часть имени файла до «_» (Т1, Л01, ЛР1-М, Башта …).
Конспекты документа — файлы в конспекты/, имя которых начинается с «<код>-» или «<код>_».
Рисунки — папка рисунки/<код>/.

Запуск: python3 tools/update_map.py   (запускается и GitHub Action после каждого push)
"""
import datetime
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP = ROOT / "КАРТА.md"
SOURCE_DIRS = sorted(p for p in ROOT.iterdir() if p.is_dir() and re.match(r"\d\d_", p.name))
NOTES, FIGS, UPLOAD = ROOT / "конспекты", ROOT / "рисунки", ROOT / "upload"
SKIP = {"README.md", ".gitkeep"}


def pdf_pages(path):
    try:
        import pymupdf
        with pymupdf.open(path) as d:
            return d.page_count
    except Exception:
        pass
    try:
        out = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True).stdout
        m = re.search(r"Pages:\s+(\d+)", out)
        return int(m.group(1)) if m else None
    except Exception:
        return None


def size(path):
    b = path.stat().st_size
    return f"{b / 1048576:.1f} МБ" if b >= 1048576 else f"{b / 1024:.0f} КБ"


def rel(path):
    return path.relative_to(ROOT).as_posix()


def files_in(folder):
    if not folder.exists():
        return []
    return sorted(p for p in folder.rglob("*") if p.is_file() and p.name not in SKIP and not p.name.startswith("."))


def notes_for(code):
    return [p for p in files_in(NOTES) if p.suffix == ".md"
            and (p.stem.startswith(code + "-") or p.stem.startswith(code + "_") or p.stem == code)]


def registry():
    lines = ["| Код | Исходный файл | Стр. | Размер | Конспекты | Рисунки |", "|---|---|---|---|---|---|"]
    for d in SOURCE_DIRS:
        for f in files_in(d):
            if f.suffix.lower() == ".md":
                continue
            code = f.stem.split("_")[0]
            pages = pdf_pages(f) if f.suffix.lower() == ".pdf" else None
            notes = notes_for(code)
            notes_s = "<br>".join(f"[{n.stem}]({rel(n)})" for n in notes) if notes else "⚠️ нет конспекта"
            figs = [p for p in files_in(FIGS / code)] if (FIGS / code).is_dir() else []
            figs_s = f"[{len(figs)} шт.]({rel(FIGS / code)}/)" if figs else "—"
            lines.append(f"| **{code}** | `{rel(f)}` | {pages or '—'} | {size(f)} | {notes_s} | {figs_s} |")
    return "\n".join(lines)


def queue():
    items = files_in(UPLOAD)
    if not items:
        return "_Пусто — всё разобрано._"
    lines = ["**⏳ Ожидают разбора** (попроси Claude: «разбери upload» — см. регламент в CLAUDE.md):", ""]
    for f in items:
        pages = pdf_pages(f) if f.suffix.lower() == ".pdf" else None
        lines.append(f"- `{rel(f)}` — {size(f)}" + (f", {pages} стр." if pages else ""))
    return "\n".join(lines)


def stats():
    n_src = sum(1 for d in SOURCE_DIRS for f in files_in(d) if f.suffix.lower() != ".md")
    n_notes = len([p for p in files_in(NOTES) if p.suffix == ".md"])
    n_figs = len(files_in(FIGS))
    n_up = len(files_in(UPLOAD))
    today = datetime.date.today().isoformat()
    return (f"Автообновление: {today} · исходников: {n_src} · конспектов: {n_notes} · "
            f"рисунков: {n_figs} · в очереди upload/: {n_up}")


def replace_block(text, name, body):
    start, end = f"<!-- AUTO:{name}:START -->", f"<!-- AUTO:{name}:END -->"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    block = f"{start}\n{body}\n{end}"
    if not pattern.search(text):
        raise SystemExit(f"В КАРТА.md нет маркеров {start} … {end}")
    return pattern.sub(lambda _: block, text)


def main():
    text = MAP.read_text(encoding="utf-8")
    new = text
    for name, body in (("STATS", stats()), ("REGISTRY", registry()), ("QUEUE", queue())):
        new = replace_block(new, name, body)
    # дата меняется каждый день — не перезаписываем файл, если изменилась только она
    strip = lambda s: re.sub(r"Автообновление: \d{4}-\d\d-\d\d", "", s)
    if strip(new) != strip(text):
        MAP.write_text(new, encoding="utf-8")
        print("КАРТА.md обновлена")
    else:
        print("КАРТА.md без изменений")


if __name__ == "__main__":
    main()
