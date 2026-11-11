# 0002: BM25 keyword search for retrieval, not embeddings

Status: accepted (Phase 5). Synthetic data, fictional company.

## Context

The onboarding agent answers product questions from a help centre of 23 short articles.
It needs to find the right article, and it needs to know when no article answers the
question, because then it must hand off rather than improvise.

## Options

1. **BM25**: rank articles by the words they share with the question, weighting rare words
   more. No model, no network, instant, and the reason for a match can be read.
2. Embeddings with a vector index: matches meaning rather than words ("add colleagues"
   finds "invite users"). Needs an embedding model (a second paid service or a local
   model), an index to rebuild when articles change, and its scores are hard to explain.
3. Hybrid search with re-ranking. Best quality at scale, most moving parts.

## Decision

BM25 (`agents/retrieval.py`), with three small additions that close most of the gap for a
corpus this size:

- The title counts three times.
- Words are cut to their first five letters, so "invite", "invited" and "invites" match.
- Articles carry a "Search keywords" line with the words customers use that the article
  does not ("add people", "stuck", "plan").

**Coverage is a rule, not a feeling.** An article covers a question when it is a strong
match (score 6 or more), or a fair match (3 or more) that contains at least 60% of the
question's meaningful words. The search tool tells the agent whether anything covers the
question, and code enforces the consequence (ADR 0003). On the test questions, all on-topic
ones are covered and all off-topic ones are not.

## Consequences

- Works offline and costs nothing, which the live demo depends on.
- When retrieval is wrong, the fix is visible: add a keyword or an article.
- It will miss paraphrases that share no words with the article. In production the agent
  model writes its own short search query, which helps; the keyword lines help more.
- The thresholds were chosen by looking at a few dozen questions. They are tested, but
  they are not learned.

## Revisit if

The help centre grows past a few hundred articles, questions arrive in several languages,
or the docs-gap list shows handoffs for questions an article does answer. Then move to
embeddings with re-ranking and keep BM25 as the first stage.
