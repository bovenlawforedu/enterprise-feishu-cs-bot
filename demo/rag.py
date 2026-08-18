"""RAG 核心：多格式（Word/PDF/网页）解析、分块、BM25 检索。
库缺失时回退 stdlib，保证任意 Python3 可直接运行；生产可换 python-docx/pdfplumber。
"""
import os, re, glob, math, json
from html.parser import HTMLParser

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
INDEX_CACHE = os.path.join(DATA, "index.json")  # 预构建索引：无第三方库也能直接加载

MIN_SCORE = 10.0  # 拒答阈值：bigram 分词后，可答/不可答分水岭约在 6.5~21，
                   # 取 10 可干净分离；G6 用黄金问答集再校准

_corpus = []
_index = None
_docs = []


def tokenize(text):
    """英文/数字按词，中文同时取单字与相邻二字（bigram）。
    bigram 可显著抑制「单字误命中」导致的幻觉式错误召回。"""
    text = (text or "").lower()
    out = re.findall(r'[a-z0-9]+', text)
    cjk = "".join(re.findall(r'[一-鿿]', text))
    out += list(cjk)
    out += [cjk[i:i + 2] for i in range(len(cjk) - 1)]
    return out


class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.k1, self.b = k1, b
        self.docs = docs
        self.N = len(docs)
        self.avgdl = (sum(len(d) for d in docs) / self.N) if self.N else 0
        self.f, self.df = [], {}
        for d in docs:
            c = {}
            for t in d:
                c[t] = c.get(t, 0) + 1
            self.f.append(c)
            for t in c:
                self.df[t] = self.df.get(t, 0) + 1

    def score(self, query):
        q = tokenize(query)
        out = []
        for i, d in enumerate(self.docs):
            s = 0.0
            dl = len(d)
            for t in set(q):
                if t in self.f[i]:
                    idf = math.log(1 + (self.N - self.df.get(t, 0) + 0.5) / (self.df.get(t, 0) + 0.5))
                    tf = self.f[i][t]
                    s += idf * (tf * (self.k1 + 1)) / (tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out.append(s)
        return out


# ---------- 解析层 ----------
def _read_docx(path):
    try:
        import docx
        lines = []
        for p in docx.Document(path).paragraphs:
            t = p.text.strip()
            if not t:
                continue
            style = (p.style.name or "") if p.style else ""
            if style.startswith("Heading"):
                lines.append("## " + t)
            else:
                lines.append(t)
        return "\n".join(lines)
    except Exception:
        import zipfile
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "ignore")
        return "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml))


def _read_pdf(path):
    try:
        import pypdf
        with open(path, "rb") as f:
            reader = pypdf.PdfReader(f)
            return "\n".join((pg.extract_text() or "") for pg in reader.pages)
    except Exception:
        with open(path, "rb") as f:
            data = f.read().decode("latin-1", "ignore")
        return " ".join(re.findall(r"\(([^)]+)\)\s*Tj", data))


class _Html2Md(HTMLParser):
    def __init__(self):
        super().__init__()
        self.lines, self.cur = [], None
    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3"):
            self.cur = "## "
    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "p") and self.cur:
            if self.cur != "## ":
                self.lines.append(self.cur)
            self.cur = None
    def handle_data(self, d):
        d = d.strip()
        if not d:
            return
        if self.cur and self.cur.startswith("## "):
            self.cur = "## " + d
        else:
            self.lines.append(d)


def _read_html(path):
    try:
        p = _Html2Md()
        p.feed(open(path, encoding="utf-8").read())
        return "\n".join(p.lines)
    except Exception:
        return re.sub(r"<[^>]+>", "\n", open(path, encoding="utf-8").read())


_READERS = {".docx": _read_docx, ".pdf": _read_pdf, ".html": _read_html, ".htm": _read_html}


# ---------- 分块层 ----------
def _split_md(text, source):
    chunks, section, buf = [], "概述", []
    def flush():
        if buf:
            chunks.append({"source": source, "section": section, "text": "\n".join(buf).strip()})
    for line in text.splitlines():
        m = re.match(r'^\s{0,3}#{1,3}\s+(.*)$', line)
        if m:
            flush(); section = m.group(1).strip(); buf = []
        else:
            buf.append(line)
    flush()
    return [c for c in chunks if c["text"].strip()]


def _split_plain(text, source):
    paras = [p.strip() for p in re.split(r"\n{1,}", text.replace("\r", "")) if p.strip()]
    chunks, buf, size = [], [], 0
    for p in paras:
        if size + len(p) > 320 and buf:
            chunks.append({"source": source, "section": "全文", "text": "\n".join(buf)})
            buf, size = [], 0
        buf.append(p); size += len(p)
    if buf:
        chunks.append({"source": source, "section": "全文", "text": "\n".join(buf)})
    return chunks


def build():
    global _corpus, _index, _docs
    _docs, _corpus = [], []
    for f in sorted(glob.glob(os.path.join(DATA, "*"))):
        ext = os.path.splitext(f)[1].lower()
        if ext not in _READERS:
            continue
        try:
            text = _READERS[ext](f)
        except Exception:
            continue
        title = os.path.splitext(os.path.basename(f))[0]
        heading_aware = ext in (".html", ".htm", ".docx")
        parts = _split_md(text, title) if heading_aware else _split_plain(text, title)
        _docs.append({"title": title, "format": ext.lstrip("."), "chars": len(text)})
        _corpus.extend(parts)
    _index = BM25([tokenize(c["text"]) for c in _corpus])
    return len(_corpus)


def list_docs():
    return _docs


def save_index():
    """把已构建语料持久化到 data/index.json，供无库环境直接加载。"""
    try:
        with open(INDEX_CACHE, "w", encoding="utf-8") as f:
            json.dump({"docs": _docs, "corpus": _corpus}, f, ensure_ascii=False)
        return True
    except Exception:
        return False


def load_index():
    """加载预构建索引（任意 Python3 零依赖即可）。成功返回 True。"""
    global _corpus, _index, _docs
    if not os.path.exists(INDEX_CACHE):
        return False
    try:
        with open(INDEX_CACHE, encoding="utf-8") as f:
            blob = json.load(f)
        _docs = blob["docs"]; _corpus = blob["corpus"]
        _index = BM25([tokenize(c["text"]) for c in _corpus])
        return True
    except Exception:
        return False


def load_or_build():
    """优先加载缓存索引；没有则实时构建并落盘。"""
    if load_index():
        return len(_corpus)
    n = build()
    save_index()
    return n


def search(query, k=3):
    if _index is None:
        load_or_build()
    scores = _index.score(query)
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:k]
    out = []
    for i in order:
        c = dict(_corpus[i]); c["score"] = round(scores[i], 3); out.append(c)
    return out


def add_doc(title, text):
    global _corpus, _index
    _corpus.extend(_split_plain(text, title))
    _index = BM25([tokenize(c["text"]) for c in _corpus])
    save_index()
    return True
