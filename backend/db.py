"""
Supabase-backed DB layer with a MongoDB-like async interface.
Runs sync Supabase client calls in asyncio.to_thread to keep endpoints async.
"""
import asyncio
from typing import Any, Dict, List, Optional

from supabase import create_client, Client


def _apply_filter(query, filter_dict: Dict[str, Any]):
    """Chain .eq() for each key in filter_dict."""
    for key, value in filter_dict.items():
        query = query.eq(key, value)
    return query


class _SupabaseCursor:
    """Cursor-like object returned by table.find().sort().to_list()."""

    def __init__(self, client: Client, table: str, filter_dict: Dict, projection: Optional[Dict]):
        self._client = client
        self._table = table
        self._filter = filter_dict
        self._projection = projection  # optional column list for select
        self._order_column: Optional[str] = None
        self._order_desc = True
        self._limit_num: Optional[int] = None

    def sort(self, key: str, direction: int):
        self._order_column = key
        self._order_desc = direction == -1
        return self

    def limit(self, n: int):
        self._limit_num = n
        return self

    async def to_list(self, n: int) -> List[Dict]:
        if self._limit_num is not None:
            n = min(n, self._limit_num)

        def _run():
            q = self._client.table(self._table).select("*")
            q = _apply_filter(q, self._filter)
            if self._order_column:
                q = q.order(self._order_column, desc=self._order_desc)
            q = q.limit(n)
            resp = q.execute()
            return list(resp.data) if resp.data else []

        return await asyncio.to_thread(_run)


class _SupabaseTable:
    """Mongo-like interface for one Supabase table."""

    def __init__(self, client: Client, table: str):
        self._client = client
        self._table = table

    def find(self, filter_dict: Dict, projection: Optional[Dict] = None) -> _SupabaseCursor:
        return _SupabaseCursor(self._client, self._table, filter_dict, projection)

    async def find_one(self, filter_dict: Dict, projection: Optional[Dict] = None) -> Optional[Dict]:
        def _run():
            q = self._client.table(self._table).select("*")
            q = _apply_filter(q, filter_dict).limit(1)
            resp = q.execute()
            if resp.data and len(resp.data) > 0:
                return dict(resp.data[0])
            return None

        return await asyncio.to_thread(_run)

    async def insert_one(self, doc: Dict) -> Optional[Dict]:
        """Insert one document. Returns the inserted row as returned by Supabase (so id matches DB)."""

        def _run():
            resp = self._client.table(self._table).insert(doc).execute()
            if resp.data and len(resp.data) > 0:
                return dict(resp.data[0])
            return None

        return await asyncio.to_thread(_run)

    async def insert_many(self, docs: List[Dict]) -> None:
        def _run():
            self._client.table(self._table).insert(docs).execute()

        await asyncio.to_thread(_run)

    async def update_one(self, filter_dict: Dict, update: Dict) -> None:
        # Only $set supported
        set_dict = update.get("$set", update)
        if not set_dict:
            return

        def _run():
            q = self._client.table(self._table).update(set_dict)
            q = _apply_filter(q, filter_dict)
            q.execute()

        await asyncio.to_thread(_run)

    async def replace_one(self, filter_dict: Dict, doc: Dict) -> None:
        # Upsert by id if present, else delete + insert
        pk = filter_dict.get("id") or (filter_dict.get("id") if "id" in filter_dict else None)
        if pk is not None and "id" in doc:
            def _run():
                self._client.table(self._table).upsert(doc, on_conflict="id").execute()
            await asyncio.to_thread(_run)
        else:
            await self.delete_many(filter_dict)
            await self.insert_one(doc)

    async def delete_many(self, filter_dict: Dict) -> None:
        def _run():
            q = self._client.table(self._table).delete()
            q = _apply_filter(q, filter_dict)
            q.execute()

        await asyncio.to_thread(_run)

    async def delete_one(self, filter_dict: Dict) -> None:
        def _run():
            q = self._client.table(self._table).delete()
            q = _apply_filter(q, filter_dict)
            q.execute()

        await asyncio.to_thread(_run)

    async def count_documents(self, filter_dict: Dict) -> int:
        def _run():
            q = self._client.table(self._table).select("id", count="exact")
            q = _apply_filter(q, filter_dict)
            resp = q.execute()
            return resp.count if hasattr(resp, "count") and resp.count is not None else len(resp.data or [])

        return await asyncio.to_thread(_run)


class _SupabaseDb:
    """Mongo-like db.manuscripts.find() etc. backed by Supabase."""

    def __init__(self, url: str, key: str):
        self._client: Client = create_client(url, key)

    @property
    def manuscripts(self) -> _SupabaseTable:
        return _SupabaseTable(self._client, "manuscripts")

    @property
    def reader_personas(self) -> _SupabaseTable:
        return _SupabaseTable(self._client, "reader_personas")

    @property
    def reader_memories(self) -> _SupabaseTable:
        return _SupabaseTable(self._client, "reader_memories")

    @property
    def reader_reactions(self) -> _SupabaseTable:
        return _SupabaseTable(self._client, "reader_reactions")

    @property
    def editor_reports(self) -> _SupabaseTable:
        return _SupabaseTable(self._client, "editor_reports")

    @property
    def users(self) -> _SupabaseTable:
        return _SupabaseTable(self._client, "users")

    @property
    def user_sessions(self) -> _SupabaseTable:
        return _SupabaseTable(self._client, "user_sessions")


def get_db(url: str, key: str) -> _SupabaseDb:
    return _SupabaseDb(url, key)
