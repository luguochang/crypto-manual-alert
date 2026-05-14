"""持久化查询边界。"""

__all__ = ["Journal", "JournalQueryRepository"]


def __getattr__(name: str):
    if name == "Journal":
        from .journal import Journal

        return Journal
    if name == "JournalQueryRepository":
        from .query_repository import JournalQueryRepository

        return JournalQueryRepository
    raise AttributeError(name)
