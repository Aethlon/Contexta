"""Shared text-analysis lexica.

These sets are needed by both the SQL lexical channel (`repositories/memory_repo.py`,
which feeds tokens to `websearch_to_tsquery`) and the in-process scorer
(`core/retrieval/engine.py`). They used to live only in the engine, so the SQL
path never saw the words the scorer already knew were noise: every extracted
memory is titled ``the user <predicate> <object>``, so the token ``user`` was
indexed at tsvector weight A in every single row and matched the entire corpus.
`user` is in both sets below, and neither path is allowed to keep a private copy:
a stopword list that only one path knows is how the channel silently degenerates
into "return everything, newest first".
"""

from __future__ import annotations

# Session and calendar vocabulary. These are constant words in this domain: the
# extraction contract stamps a session id and a normalised timestamp on every
# memory, and the operator phrases questions with them ("what did I say in the
# last session", "anything from last week"). They carry no discriminative power
# on either path, and `RetrievalEngine._keyword_score` downweights them to 0.25
# rather than dropping them, which is why they have to be present in the set the
# engine consults -- and in the set the SQL channel consults, which drops them.
#
# They are kept in their own frozenset because an earlier refactor removed all 19
# from this file at once, and both consumers silently degraded together. The
# union is what both paths need; do not let these words get pruned again.
SESSION_AND_TEMPORAL_STOPWORDS: frozenset[str] = frozenset(
    {
        "assistant", "chat", "clock", "conversation", "date", "day", "hour",
        "minute", "month", "session", "speaker", "system", "time", "today",
        "tomorrow", "turn", "week", "year", "yesterday",
    }
)

# Discourse words that carry no retrieval signal. `user` is the important one:
# the extraction contract fixes `subject` to the literal string "the user", so
# it is not a rare term here, it is a constant.
DISCOURSE_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
        "any", "are", "as", "at", "be", "because", "been", "before", "being", "below",
        "between", "both", "but", "by",
        "can", "could",
        "did", "do", "does", "doing", "down", "during",
        "each", "few", "for", "from", "further",
        "had", "has", "have", "having", "he", "her", "here", "hers", "him", "his",
        "how",
        "i", "if", "in", "into", "is", "it", "its", "itself",
        "just",
        "me", "more", "most", "my",
        "no", "nor", "not", "now",
        "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours",
        "out", "over", "own",
        "same", "she", "should", "so", "some", "such",
        "than", "that", "the", "their", "theirs", "them", "then", "there", "these",
        "they", "this", "those", "through", "to", "too",
        "under", "until", "up", "user", "using",
        "very",
        "was", "we", "were", "what", "when", "where", "which", "while", "who",
        "whom", "why", "will", "with", "would",
        "you", "your", "yours",
    }
) | SESSION_AND_TEMPORAL_STOPWORDS

# Words already handled by PostgreSQL's english text-search configuration, which
# strips them during `to_tsvector`. Sending them in the tsquery adds nothing.
#
# A subset of DISCOURSE_STOPWORDS, plus the session/calendar vocabulary. The SQL
# channel can afford to be stricter than the in-process scorer: it drops noise
# tokens from the tsquery entirely instead of downweighting them, so a
# stopword-only query returns nothing rather than every row.
LEXICAL_STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "about", "after", "all", "am", "an", "and", "are", "as", "at",
        "be", "been", "being", "by",
        "did", "do", "does",
        "for", "from",
        "had", "has", "have", "he", "her", "here", "him", "his", "how",
        "i", "if", "in", "into", "is", "it", "its",
        "me", "my",
        "no", "nor", "not",
        "of", "on", "once", "only", "or", "other", "our", "out", "over", "own",
        "same", "she", "should", "so", "some", "such",
        "than", "that", "the", "their", "them", "then", "there", "these",
        "they", "this", "those", "through", "to", "too",
        "up", "user",
        "was", "we", "were", "what", "when", "where", "which", "while", "who",
        "whom", "why", "will", "with",
        "you", "your",
    }
) | SESSION_AND_TEMPORAL_STOPWORDS


def informative_terms(tokens: list[str]) -> list[str]:
    """Keep only tokens that can discriminate between memories.

    Both retrieval paths need at least one survivor: a query made entirely of
    noise is not a weak match against the corpus, it is a match against every
    row, so the callers turn an empty result into a deliberate "no lexical
    candidates" rather than a full scan.
    """
    return [token for token in tokens if token not in LEXICAL_STOPWORDS]
