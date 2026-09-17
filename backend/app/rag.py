"""RAG 检索层：题库加载 + TF-IDF 向量索引。

与向量数据库的使用方式一致（build 索引 -> query 检索 Top-K），
生产环境可平滑替换为 Embedding 模型 + Milvus/pgvector，只需实现同一接口。
"""
import json
import math
import re
from collections import Counter
from pathlib import Path

from .config import BANK_DIR

_ASCII_WORD = re.compile(r"[a-zA-Z0-9_]+")
_STOP_CHARS = set("的了是在和与或对中有请以及而为并等把被向从到比更很")
_GENERIC_WORDS = {
    "the", "and", "for", "with", "what", "why", "how", "when", "which",
    "introduce", "explain", "describe", "example", "examples", "vs",
}


def tokenize(text: str) -> list[str]:
    """中文按字符二元组、英文数字按词切分（无外部分词依赖）。"""
    text = text.lower()
    tokens = _ASCII_WORD.findall(text)
    cleaned = "".join(ch for ch in text if "\u4e00" <= ch <= "\u9fff" and ch not in _STOP_CHARS)
    tokens.extend(cleaned[i:i + 2] for i in range(len(cleaned) - 1))
    return [t for t in tokens if t]


def key_terms(text: str) -> set[str]:
    """提取用于要点匹配的关键词集合。"""
    terms = set()
    for token in tokenize(text):
        if token in _GENERIC_WORDS or len(token) < 2:
            continue
        terms.add(token)
    return terms


class TfidfIndex:
    """轻量 TF-IDF 余弦相似度索引。"""

    def __init__(self) -> None:
        self.docs: list[dict] = []  # {doc_id, text, meta}
        self._idf: dict[str, float] = {}
        self._vectors: list[dict[str, float]] = []
        self._norms: list[float] = []

    def add(self, doc_id: str, text: str, meta: dict) -> None:
        self.docs.append({"doc_id": doc_id, "text": text, "meta": meta})

    def build(self) -> None:
        df: Counter = Counter()
        tfs: list[Counter] = []
        for doc in self.docs:
            tf = Counter(tokenize(doc["text"]))
            tfs.append(tf)
            for term in tf:
                df[term] += 1
        n = len(self.docs)
        self._idf = {t: math.log((n + 1) / (c + 1)) + 1.0 for t, c in df.items()}
        self._vectors = [{t: c * self._idf[t] for t, c in tf.items()} for tf in tfs]
        self._norms = [
            math.sqrt(sum(v * v for v in vec.values())) or 1.0 for vec in self._vectors
        ]

    def search(self, query: str, top_k: int = 5, filter_fn=None) -> list[tuple[str, float, dict]]:
        """返回 [(doc_id, score, meta)]，按相似度降序。"""
        if not self._vectors:
            return []
        tf = Counter(tokenize(query))
        qvec = {t: c * self._idf[t] for t, c in tf.items() if t in self._idf}
        if not qvec:
            return []
        qnorm = math.sqrt(sum(v * v for v in qvec.values())) or 1.0
        scored = []
        for i, vec in enumerate(self._vectors):
            meta = self.docs[i]["meta"]
            if filter_fn is not None and not filter_fn(meta):
                continue
            dot = sum(w * vec[t] for t, w in qvec.items() if t in vec)
            if dot <= 0:
                continue
            scored.append((dot / (qnorm * self._norms[i]), i))
        scored.sort(key=lambda pair: -pair[0])
        return [
            (self.docs[i]["doc_id"], round(score, 4), self.docs[i]["meta"])
            for score, i in scored[:top_k]
        ]


class KnowledgeBase:
    """题库：加载、索引、检索与管理（增删改热更新）。"""

    def __init__(self) -> None:
        self.questions: dict[str, dict] = {}
        self.by_skill: dict[str, list[dict]] = {}
        self.skill_files: dict[str, Path] = {}
        self.index = TfidfIndex()

    def _reset(self) -> None:
        self.questions.clear()
        self.by_skill.clear()
        self.skill_files.clear()
        self.index = TfidfIndex()

    def load(self) -> None:
        for path in sorted(BANK_DIR.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            for q in data:
                qid = q["id"]
                self.questions[qid] = q
                self.by_skill.setdefault(q["skill"], []).append(q)
                self.skill_files.setdefault(q["skill"], path)
                text = f"{q['question']} {' '.join(q['key_points'])} {q['skill']}"
                self.index.add(qid, text, q)
        self.index.build()

    def reload(self) -> None:
        """题库文件变更后重建索引（热更新，无需重启）。"""
        self._reset()
        self.load()

    def stats(self) -> dict[str, int]:
        return {skill: len(questions) for skill, questions in sorted(self.by_skill.items())}

    def search(
        self,
        query: str,
        skill: str | None = None,
        difficulty: str | None = None,
        top_k: int = 5,
    ) -> list[tuple[str, float, dict]]:
        """按技能/难度过滤的语义检索（RAG 核心入口）。"""

        def _filter(meta: dict) -> bool:
            if skill and meta["skill"] != skill:
                return False
            if difficulty and meta["difficulty"] != difficulty:
                return False
            return True

        return self.index.search(query, top_k=top_k, filter_fn=_filter)

    # ---------- 题库管理（管理员） ----------

    @staticmethod
    def _prefix_from_skill(skill: str) -> str:
        prefix = re.sub(r"[^A-Za-z0-9]", "", skill).upper()[:2]
        return (prefix + "XX")[:2]

    def _gen_qid(self, skill: str) -> str:
        """沿用该技能已有 ID 的前缀；新技能则从技能名派生前缀。"""
        skill_ids = [q["id"] for q in self.by_skill.get(skill, [])]
        if skill_ids:
            prefix = Counter(q[:2].upper() for q in skill_ids).most_common(1)[0][0]
            if not (len(prefix) == 2 and prefix.isalnum()):
                prefix = self._prefix_from_skill(skill)
        else:
            prefix = self._prefix_from_skill(skill)
        n = 1
        while f"{prefix}{n:02d}" in self.questions:
            n += 1
        return f"{prefix}{n:02d}"

    def _bank_path_for(self, skill: str) -> Path:
        slug = re.sub(r"[^a-z0-9]+", "-", skill.lower()).strip("-") or "custom"
        return BANK_DIR / f"{slug}.json"

    @staticmethod
    def _write_bank(path: Path, questions: list[dict]) -> None:
        path.write_text(
            json.dumps(questions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    @staticmethod
    def _q_record(data: dict, qid: str) -> dict:
        return {
            "id": qid,
            "skill": data["skill"],
            "difficulty": data["difficulty"],
            "question": data["question"],
            "key_points": list(data["key_points"]),
            "reference_answer": data["reference_answer"],
            "follow_ups": list(data.get("follow_ups", [])),
        }

    def add_question(self, data: dict) -> dict:
        qid = (data.get("qid") or "").strip().upper() or self._gen_qid(data["skill"])
        if qid in self.questions:
            raise ValueError(f"题目 ID「{qid}」已存在")
        q = self._q_record(data, qid)
        path = self.skill_files.get(q["skill"]) or self._bank_path_for(q["skill"])
        questions = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        questions.append(q)
        self._write_bank(path, questions)
        self.reload()
        return q

    def update_question(self, qid: str, data: dict) -> dict:
        old = self.questions.get(qid)
        if old is None:
            raise ValueError("题目不存在")
        merged = self._q_record(data, qid)
        old_path = self.skill_files.get(old["skill"])
        if old_path and old_path.exists():
            remaining = [
                q for q in json.loads(old_path.read_text(encoding="utf-8")) if q["id"] != qid
            ]
            self._write_bank(old_path, remaining)
        path = self.skill_files.get(merged["skill"]) or self._bank_path_for(merged["skill"])
        questions = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        questions.append(merged)
        self._write_bank(path, questions)
        self.reload()
        return merged

    def delete_question(self, qid: str) -> None:
        q = self.questions.get(qid)
        if q is None:
            raise ValueError("题目不存在")
        path = self.skill_files.get(q["skill"])
        if path and path.exists():
            remaining = [
                x for x in json.loads(path.read_text(encoding="utf-8")) if x["id"] != qid
            ]
            self._write_bank(path, remaining)
        self.reload()


kb = KnowledgeBase()
