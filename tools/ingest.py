#!/usr/bin/env python3
"""Конвертирует материалы из upload/ в формат, удобный для Claude.

Для каждого файла создаётся knowledge/<подпапка как в upload>/<slug>/
(например upload/labs/x.pdf -> knowledge/labs/x/):
  text/pNNN-MMM.md   текст по 10 страниц, перед каждой страницей маркер "=== Страница N ==="
  pages/NNN.jpg      картинка каждой страницы (формулы, графики, схемы смотреть здесь)
  meta.json          метаданные (хэш исходника, число страниц, оглавление)
и обновляется knowledge/INDEX.md.

Использование:  python3 tools/ingest.py [--force]
Зависимости:    pip install pymupdf  (для docx/pptx ещё libreoffice)
"""
import hashlib, json, re, shutil, subprocess, sys, tempfile
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parent.parent
UPLOAD, OUT = ROOT / "upload", ROOT / "knowledge"
CHUNK, DPI, QUALITY = 10, 100, 55
OFFICE = {".docx", ".doc", ".pptx", ".ppt", ".odt", ".odp", ".rtf"}

TR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюяіїє",
              ["a","b","v","g","d","e","e","zh","z","i","y","k","l","m","n","o","p","r","s","t","u","f","h","c","ch","sh","sch","","y","","e","yu","ya","i","yi","ye"]))

# короткие имена для папок (ключ — имя файла без расширения); остальное транслитерируется
SLUGS = {"Башта Т.М. 2010 Гидравлика, гидромашины и гидроприводы": "bashta-gidravlika"}

def slugify(name):
    if name in SLUGS:
        return SLUGS[name]
    s = "".join(TR.get(c, c) for c in name.lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:60] or "doc"

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def to_pdf(src, tmp):
    subprocess.run(["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", str(tmp), str(src)],
                   check=True, capture_output=True)
    return tmp / (src.stem + ".pdf")

def toc_of(doc, texts):
    toc = [(lvl, t.strip(), pg) for lvl, t, pg in doc.get_toc()]
    if toc:
        return [f"{'  ' * (l - 1)}- {t} (стр. {p})" for l, t, p in toc]
    pat = re.compile(r"^(?:(?:ЛЕКЦИЯ|ГЛАВА|РАЗДЕЛ|ЧАСТЬ|ТЕТРАДЬ)\s*[\dIVX]+|§\s*\d+\.\d+|ВВЕДЕНИЕ)\b.{0,90}$", re.I)
    out, seen = [], set()
    for i, t in enumerate(texts, 1):
        for line in t.splitlines()[:25]:
            line = re.sub(r"\s+", " ", line).strip()
            if pat.match(line) and line not in seen:
                seen.add(line)
                out.append(f"- {line} (стр. {i})")
    return out

def convert(src, dst):
    tmp = Path(tempfile.mkdtemp())
    try:
        pdf = to_pdf(src, tmp) if src.suffix.lower() in OFFICE else src
        doc = pymupdf.open(pdf)
        if dst.exists():
            shutil.rmtree(dst)
        (dst / "text").mkdir(parents=True)
        (dst / "pages").mkdir()
        texts = []
        for i, page in enumerate(doc, 1):
            texts.append(page.get_text("text", sort=True).strip())
            pix = page.get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
            (dst / "pages" / f"{i:03d}.jpg").write_bytes(pix.tobytes("jpeg", jpg_quality=QUALITY))
        n = len(texts)
        for a in range(0, n, CHUNK):
            b = min(a + CHUNK, n)
            body = "\n\n".join(f"=== Страница {i} ===\n{texts[i - 1]}" for i in range(a + 1, b + 1))
            (dst / "text" / f"p{a + 1:03d}-{b:03d}.md").write_text(body + "\n", encoding="utf-8")
        toc = toc_of(doc, texts)
        meta = {"source": str(src.relative_to(ROOT)), "sha256": sha(src), "pages": n,
                "chars": sum(map(len, texts)), "toc": toc}
        (dst / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        return meta
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def write_index():
    lines = ["# Индекс базы знаний", "",
             "Автогенерируется `tools/ingest.py`. Как пользоваться — см. `/CLAUDE.md`.", ""]
    for m in sorted(OUT.glob("**/meta.json")):
        d = json.loads(m.read_text(encoding="utf-8"))
        lines += [f"## `{m.parent.relative_to(OUT)}` — {Path(d['source']).name}",
                  f"Страниц: {d['pages']} · исходник: `{d['source']}`", ""]
        if d["toc"]:
            lines += ["<details><summary>Оглавление</summary>", ""] + d["toc"][:300] + ["", "</details>", ""]
    (OUT / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")

def main():
    force = "--force" in sys.argv
    OUT.mkdir(exist_ok=True)
    for src in sorted(UPLOAD.rglob("*")):
        if not src.is_file() or src.suffix.lower() not in OFFICE | {".pdf"}:
            continue
        dst = OUT / src.parent.relative_to(UPLOAD) / slugify(src.stem)
        meta = dst / "meta.json"
        if not force and meta.exists() and json.loads(meta.read_text())["sha256"] == sha(src):
            print("skip", src.name)
            continue
        print("convert", src.name, flush=True)
        m = convert(src, dst)
        print(f"  -> {dst.name}: {m['pages']} стр.")
    write_index()

if __name__ == "__main__":
    main()
