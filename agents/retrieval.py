"""Find the help articles that answer a question (BM25 keyword search).

Synthetic data, fictional company. The knowledge base is the folder kb/: about
twenty short help articles for the fictional product.

BM25 ranks articles by the words they share with the question, giving more weight
to rarer words. It is simple, fast, needs no model and no network, and its result
can be explained: "this article matched on 'SSO', 'metadata' and 'certificate'".
See docs/decisions/0002-bm25-retrieval.md for why not embeddings.

The search also answers a second question: do the docs cover this at all? An
article "covers" a question when it is a strong match, or a fair match that also
contains most of the question's meaningful words. If nothing covers the question,
the agent must not improvise an answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from rank_bm25 import BM25Okapi

from common.paths import ROOT

KB_DIR = ROOT / "kb"
# What "covered" means: a strong match on its own, or a fair match that also contains
# most of the question's meaningful words. Chosen by looking at real questions
# (tests/test_agents.py keeps it honest): on-topic questions pass, off-topic ones do not.
STRONG_SCORE = 6.0
MIN_SCORE = 3.0
MIN_COVERAGE = 0.6

STOPWORDS = set(
    "a an and are as at be by can do does for from how i if in is it my of on or our so that "
    "the there this to we what when where which who why will with you your me us have has "
    "not no yes please thanks thank hi hello would could should need want relay about just "
    "really some any got get also them they their".split()
)


@dataclass
class Article:
    slug: str
    title: str
    text: str


def tokens(text: str) -> list[str]:
    """Lowercase words, without the very common ones, cut to their first five letters.

    Cutting to five letters is a crude way to make "invite", "invited" and "invites"
    count as the same word.
    """
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [word[:5] for word in words if word not in STOPWORDS]


class KnowledgeBase:
    def __init__(self, folder: Path = KB_DIR):
        self.articles = []
        for path in sorted(folder.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            title = text.splitlines()[0].removeprefix("# ").strip()
            body = text.split("\n---\n")[0]  # drop the footer
            self.articles.append(Article(path.stem, title, body))
        # The title is counted three times: a match in the title matters more.
        self.corpus = [tokens(f"{a.title} {a.title} {a.title} {a.text}") for a in self.articles]
        self.index = BM25Okapi(self.corpus)

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """The best-matching articles, best first, each with its score and coverage."""
        query_words = tokens(query)
        scores = self.index.get_scores(query_words)
        ranked = sorted(
            zip(scores, self.articles, self.corpus, strict=True), key=lambda item: -item[0]
        )
        results = []
        for score, article, article_words in ranked[:top_k]:
            if score <= 0:
                continue
            wanted = set(query_words)
            coverage = len(wanted & set(article_words)) / len(wanted) if wanted else 0.0
            results.append(
                {
                    "slug": article.slug,
                    "title": article.title,
                    "score": round(float(score), 2),
                    "coverage": round(coverage, 2),
                    "covers_question": bool(
                        score >= STRONG_SCORE or (score >= MIN_SCORE and coverage >= MIN_COVERAGE)
                    ),
                    "text": article.text,
                }
            )
        return results


@lru_cache(maxsize=1)
def knowledge_base() -> KnowledgeBase:
    """The knowledge base, loaded once."""
    return KnowledgeBase()
