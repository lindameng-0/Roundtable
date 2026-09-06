"""
Supabase-backed DB layer with a MongoDB-like async interface.
Runs sync Supabase client calls in asyncio.to_thread to keep endpoints async.
"""
import asyncio
import copy
import uuid
import json
from pathlib import Path
from datetime import datetime
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

    @property
    def email_verification_tokens(self) -> _SupabaseTable:
        return _SupabaseTable(self._client, "email_verification_tokens")

    @property
    def password_reset_tokens(self) -> _SupabaseTable:
        return _SupabaseTable(self._client, "password_reset_tokens")

    @property
    def oauth_states(self) -> _SupabaseTable:
        return _SupabaseTable(self._client, "oauth_states")

    @property
    def waitlist(self) -> _SupabaseTable:
        return _SupabaseTable(self._client, "waitlist")

    @property
    def feedback(self) -> _SupabaseTable:
        return _SupabaseTable(self._client, "feedback")

    @property
    def report_versions(self) -> _SupabaseTable:
        return _SupabaseTable(self._client, "report_versions")

    @property
    def workflow_tasks(self) -> _SupabaseTable:
        return _SupabaseTable(self._client, "workflow_tasks")

    @property
    def cost_reservations(self) -> _SupabaseTable:
        return _SupabaseTable(self._client, "cost_reservations")

    async def reserve_cost(self, reservation_id, manuscript_id, role, operation_key, estimated_cost_usd):
        def _run():
            response = self._client.rpc("reserve_ai_cost", {
                "p_reservation_id": reservation_id, "p_manuscript_id": manuscript_id,
                "p_role": role, "p_operation_key": operation_key,
                "p_estimated_cost_usd": estimated_cost_usd,
            }).execute()
            return dict(response.data or {})
        return await asyncio.to_thread(_run)

    async def settle_cost(self, reservation_id, actual_cost_usd):
        await asyncio.to_thread(lambda: self._client.rpc("settle_ai_cost", {
            "p_reservation_id": reservation_id, "p_actual_cost_usd": actual_cost_usd,
        }).execute())

    async def release_cost(self, reservation_id):
        await asyncio.to_thread(lambda: self._client.rpc("release_ai_cost", {
            "p_reservation_id": reservation_id,
        }).execute())

    async def cleanup_stale_cost_reservations(self):
        def _run():
            response = self._client.rpc("release_stale_ai_cost", {"p_older_than_minutes": 120}).execute()
            return int(response.data or 0)
        return await asyncio.to_thread(_run)


def get_db(url: str, key: str) -> _SupabaseDb:
    return _SupabaseDb(url, key)


_JSON_COLUMNS = {
    "manuscripts": {"comparable_books", "sections"},
    "reader_personas": {"liked_tropes", "disliked_tropes", "secondary_focuses"},
    "reader_memories": {"memory_json"},
    "reader_reactions": {"inline_comments", "response_json"},
    "editor_reports": {"report_json"},
    "report_versions": {"report_json"},
}

_TIMESTAMP_COLUMNS = {"created_at", "updated_at", "expires_at", "used_at"}


class _PostgresCursor:
    def __init__(self, database: "_PostgresDb", table: str, filters: Dict[str, Any]):
        self._database, self._table, self._filters = database, table, filters
        self._order_column, self._order_desc, self._limit_num = None, True, None

    def sort(self, key: str, direction: int):
        self._database.validate_name(key)
        self._order_column, self._order_desc = key, direction == -1
        return self

    def limit(self, n: int):
        self._limit_num = n
        return self

    async def to_list(self, n: int) -> List[Dict]:
        limit = min(n, self._limit_num) if self._limit_num is not None else n
        return await self._database.fetch(self._table, self._filters, self._order_column, self._order_desc, limit)


class _PostgresTable:
    def __init__(self, database: "_PostgresDb", name: str):
        self._database, self._name = database, name

    def find(self, filter_dict: Dict, projection: Optional[Dict] = None) -> _PostgresCursor:
        return _PostgresCursor(self._database, self._name, filter_dict)

    async def find_one(self, filter_dict: Dict, projection: Optional[Dict] = None) -> Optional[Dict]:
        rows = await self._database.fetch(self._name, filter_dict, None, True, 1)
        return rows[0] if rows else None

    async def insert_one(self, doc: Dict) -> Dict:
        return await self._database.insert(self._name, doc)

    async def insert_many(self, docs: List[Dict]) -> None:
        for doc in docs:
            await self.insert_one(doc)

    async def update_one(self, filter_dict: Dict, update: Dict) -> None:
        await self._database.update(self._name, filter_dict, update.get("$set", update))

    async def replace_one(self, filter_dict: Dict, doc: Dict) -> None:
        if await self.find_one(filter_dict):
            await self.update_one(filter_dict, {"$set": doc})
        else:
            await self.insert_one(doc)

    async def delete_many(self, filter_dict: Dict) -> None:
        await self._database.delete(self._name, filter_dict, one=False)

    async def delete_one(self, filter_dict: Dict) -> None:
        await self._database.delete(self._name, filter_dict, one=True)

    async def count_documents(self, filter_dict: Dict) -> int:
        return await self._database.count(self._name, filter_dict)


class _PostgresDb:
    TABLES = {
        "manuscripts", "reader_personas", "reader_memories", "reader_reactions",
        "editor_reports", "report_versions", "workflow_tasks", "users", "user_sessions",
        "email_verification_tokens", "password_reset_tokens", "oauth_states",
        "rate_limit_buckets", "waitlist", "feedback", "cost_reservations",
    }

    def __init__(self, url: str, migrations_dir: Path):
        self._url, self._migrations_dir, self._pool = url, Path(migrations_dir), None

    def __getattr__(self, name: str) -> _PostgresTable:
        if name in self.TABLES:
            return _PostgresTable(self, name)
        raise AttributeError(name)

    @staticmethod
    def validate_name(value: str) -> None:
        if not value or not value.replace("_", "").isalnum():
            raise ValueError("Invalid database identifier")

    def _validate_table(self, table: str) -> None:
        if table not in self.TABLES:
            raise ValueError("Invalid database table")

    async def initialize(self) -> None:
        if self._pool:
            return
        import asyncpg
        self._pool = await asyncpg.create_pool(self._url, min_size=1, max_size=10, command_timeout=60)
        async with self._pool.acquire() as conn:
            await conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
            applied = {row["version"] for row in await conn.fetch("SELECT version FROM schema_migrations")}
            for path in sorted(self._migrations_dir.glob("*.sql")):
                if path.name in applied:
                    continue
                async with conn.transaction():
                    await conn.execute(path.read_text(encoding="utf-8"))
                    await conn.execute("INSERT INTO schema_migrations(version) VALUES($1)", path.name)
            await conn.execute("DELETE FROM oauth_states WHERE expires_at <= now()")
            await conn.execute("DELETE FROM rate_limit_buckets WHERE expires_at <= now()")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def ping(self) -> bool:
        return bool(self._pool and await self._pool.fetchval("SELECT TRUE"))

    def _where(self, filters: Dict[str, Any], offset: int = 1):
        clauses, values = [], []
        for index, (key, value) in enumerate(filters.items(), offset):
            self.validate_name(key)
            if value is None:
                clauses.append(f'"{key}" IS NULL')
            else:
                placeholder = offset + len(values)
                clauses.append(f'"{key}" = ${placeholder}')
                values.append(self._value("", key, value))
        return (" WHERE " + " AND ".join(clauses) if clauses else "", values)

    def _decode(self, table: str, row) -> Dict:
        data = dict(row)
        for key in _JSON_COLUMNS.get(table, set()):
            if isinstance(data.get(key), str):
                data[key] = json.loads(data[key])
        for key, value in list(data.items()):
            if hasattr(value, "isoformat"):
                data[key] = value.isoformat()
        return data

    def _value(self, table: str, key: str, value: Any):
        if key in _JSON_COLUMNS.get(table, set()):
            return json.dumps(value, ensure_ascii=False)
        if key in _TIMESTAMP_COLUMNS and isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value

    async def fetch(self, table, filters, order, desc, limit):
        self._validate_table(table)
        where, values = self._where(filters)
        order_sql = f' ORDER BY "{order}" {"DESC" if desc else "ASC"}' if order else ""
        rows = await self._pool.fetch(f'SELECT * FROM "{table}"{where}{order_sql} LIMIT ${len(values)+1}', *values, limit)
        return [self._decode(table, row) for row in rows]

    async def insert(self, table, doc):
        self._validate_table(table)
        data = dict(doc)
        if table != "users":
            data.setdefault("id", str(uuid.uuid4()))
        columns = list(data)
        for key in columns: self.validate_name(key)
        values = [self._value(table, key, data[key]) for key in columns]
        quoted = ", ".join('"' + key + '"' for key in columns)
        placeholders = ", ".join(f"${i}" for i in range(1, len(values) + 1))
        row = await self._pool.fetchrow(f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders}) RETURNING *', *values)
        return self._decode(table, row)

    async def update(self, table, filters, values):
        self._validate_table(table)
        if not values: return
        columns = list(values)
        for key in columns: self.validate_name(key)
        args = [self._value(table, key, values[key]) for key in columns]
        assignments = ", ".join(f'"{key}" = ${i}' for i, key in enumerate(columns, 1))
        where, filter_values = self._where(filters, len(args) + 1)
        await self._pool.execute(f'UPDATE "{table}" SET {assignments}{where}', *(args + filter_values))

    async def delete(self, table, filters, one=False):
        self._validate_table(table)
        where, values = self._where(filters)
        sql = f'DELETE FROM "{table}"{where}'
        if one:
            sql = f'DELETE FROM "{table}" WHERE ctid IN (SELECT ctid FROM "{table}"{where} LIMIT 1)'
        await self._pool.execute(sql, *values)

    async def count(self, table, filters):
        self._validate_table(table)
        where, values = self._where(filters)
        return int(await self._pool.fetchval(f'SELECT count(*) FROM "{table}"{where}', *values))

    async def consume_oauth_state(self, token_hash: str) -> bool:
        row = await self._pool.fetchrow(
            "DELETE FROM oauth_states WHERE token_hash = $1 AND expires_at > now() RETURNING id",
            token_hash,
        )
        return row is not None

    async def consume_rate_limit(self, key: str, limit: int, window_seconds: int):
        row = await self._pool.fetchrow(
            """
            INSERT INTO rate_limit_buckets(key, count, expires_at)
            VALUES($1, 1, now() + make_interval(secs => $2))
            ON CONFLICT(key) DO UPDATE SET
              count = CASE WHEN rate_limit_buckets.expires_at <= now()
                           THEN 1 ELSE rate_limit_buckets.count + 1 END,
              expires_at = CASE WHEN rate_limit_buckets.expires_at <= now()
                                THEN now() + make_interval(secs => $2)
                                ELSE rate_limit_buckets.expires_at END
            RETURNING count,
              GREATEST(1, CEIL(EXTRACT(EPOCH FROM (expires_at - now()))))::int AS retry_after
            """,
            key,
            window_seconds,
        )
        return {"allowed": int(row["count"]) <= limit, "retry_after": int(row["retry_after"])}

    async def reserve_cost(self, reservation_id, manuscript_id, role, operation_key, estimated_cost_usd):
        value = await self._pool.fetchval(
            "SELECT reserve_ai_cost($1, $2, $3, $4, $5)",
            reservation_id, manuscript_id, role, operation_key, estimated_cost_usd,
        )
        return json.loads(value) if isinstance(value, str) else dict(value)

    async def settle_cost(self, reservation_id, actual_cost_usd):
        await self._pool.execute("SELECT settle_ai_cost($1, $2)", reservation_id, actual_cost_usd)

    async def release_cost(self, reservation_id):
        await self._pool.execute("SELECT release_ai_cost($1)", reservation_id)

    async def cleanup_stale_cost_reservations(self):
        return int(await self._pool.fetchval("SELECT release_stale_ai_cost(120)"))


def get_postgres_db(url: str, migrations_dir: Path) -> _PostgresDb:
    return _PostgresDb(url, migrations_dir)


def _matches(document: Dict[str, Any], filters: Dict[str, Any]) -> bool:
    return all(document.get(key) == value for key, value in filters.items())


class _MemoryCursor:
    def __init__(self, table: "_MemoryTable", filter_dict: Dict[str, Any]):
        self._table = table
        self._filter = filter_dict
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
        rows = [copy.deepcopy(row) for row in self._table._rows if _matches(row, self._filter)]
        if self._order_column:
            rows.sort(
                key=lambda row: (row.get(self._order_column) is not None, row.get(self._order_column)),
                reverse=self._order_desc,
            )
        limit = min(n, self._limit_num) if self._limit_num is not None else n
        return rows[:limit]


class _MemoryTable:
    """Small async Mongo-like table used for local development and tests."""

    def __init__(self, name: str, rows: List[Dict]):
        self._name = name
        self._rows = rows

    def find(self, filter_dict: Dict, projection: Optional[Dict] = None) -> _MemoryCursor:
        return _MemoryCursor(self, filter_dict)

    async def find_one(self, filter_dict: Dict, projection: Optional[Dict] = None) -> Optional[Dict]:
        for row in self._rows:
            if _matches(row, filter_dict):
                return copy.deepcopy(row)
        return None

    def _unique_key(self, document: Dict) -> Optional[tuple]:
        if document.get("id") is not None:
            return ("id", document["id"])
        if self._name == "users" and document.get("user_id"):
            return ("user_id", document["user_id"])
        return None

    def _has_conflict(self, document: Dict) -> bool:
        key = self._unique_key(document)
        if key and any(row.get(key[0]) == key[1] for row in self._rows):
            return True
        unique_fields = {
            "users": "email",
            "user_sessions": "token_hash",
            "oauth_states": "token_hash",
            "waitlist": "email",
            "editor_reports": "manuscript_id",
        }
        unique_field = unique_fields.get(self._name)
        if unique_field and document.get(unique_field) is not None:
            return any(row.get(unique_field) == document.get(unique_field) for row in self._rows)
        if self._name in {"reader_reactions", "reader_memories"}:
            composite = ("manuscript_id", "reader_id", "section_number")
            return any(all(row.get(key) == document.get(key) for key in composite) for row in self._rows)
        if self._name == "report_versions":
            return any(
                row.get("manuscript_id") == document.get("manuscript_id")
                and row.get("version") == document.get("version")
                for row in self._rows
            )
        return False

    async def insert_one(self, doc: Dict) -> Dict:
        document = copy.deepcopy(doc)
        document.setdefault("id", str(uuid.uuid4()))
        if self._has_conflict(document):
            raise ValueError("duplicate key value violates unique constraint (23505)")
        self._rows.append(document)
        return copy.deepcopy(document)

    async def insert_many(self, docs: List[Dict]) -> None:
        for doc in docs:
            await self.insert_one(doc)

    async def update_one(self, filter_dict: Dict, update: Dict) -> None:
        set_dict = update.get("$set", update)
        for row in self._rows:
            if _matches(row, filter_dict):
                row.update(copy.deepcopy(set_dict))

    async def replace_one(self, filter_dict: Dict, doc: Dict) -> None:
        for index, row in enumerate(self._rows):
            if _matches(row, filter_dict):
                self._rows[index] = copy.deepcopy(doc)
                return
        await self.insert_one(doc)

    async def delete_many(self, filter_dict: Dict) -> None:
        self._rows[:] = [row for row in self._rows if not _matches(row, filter_dict)]

    async def delete_one(self, filter_dict: Dict) -> None:
        for index, row in enumerate(self._rows):
            if _matches(row, filter_dict):
                del self._rows[index]
                return

    async def count_documents(self, filter_dict: Dict) -> int:
        return sum(1 for row in self._rows if _matches(row, filter_dict))


class _MemoryDb:
    """Process-local database. Data is intentionally cleared on restart."""

    TABLES = (
        "manuscripts",
        "reader_personas",
        "reader_memories",
        "reader_reactions",
        "editor_reports",
        "users",
        "user_sessions",
        "email_verification_tokens",
        "password_reset_tokens",
        "oauth_states",
        "waitlist",
        "feedback",
        "workflow_tasks",
        "report_versions",
        "cost_reservations",
    )

    def __init__(self):
        self._data: Dict[str, List[Dict]] = {name: [] for name in self.TABLES}
        self._tables = {name: _MemoryTable(name, self._data[name]) for name in self.TABLES}
        self._cost_lock = asyncio.Lock()

    def __getattr__(self, name: str) -> _MemoryTable:
        if name in self._tables:
            return self._tables[name]
        raise AttributeError(name)

    def clear(self) -> None:
        for rows in self._data.values():
            rows.clear()

    async def reserve_cost(self, reservation_id, manuscript_id, role, operation_key, estimated_cost_usd):
        async with self._cost_lock:
            manuscript = next((row for row in self._data["manuscripts"] if row.get("id") == manuscript_id), None)
            if manuscript is None:
                raise ValueError("Manuscript not found")
            limit = float(manuscript.get("cost_limit_usd", 25) or 0)
            spent = float(manuscript.get("cost_spent_usd") or 0)
            reserved = float(manuscript.get("cost_reserved_usd") or 0)
            estimate = float(estimated_cost_usd)
            if limit > 0 and spent + reserved + estimate > limit:
                return {"reserved": False, "limit_usd": limit, "spent_usd": spent, "reserved_usd": reserved, "requested_usd": estimate}
            manuscript["cost_reserved_usd"] = reserved + estimate
            self._data["cost_reservations"].append({
                "id": reservation_id, "manuscript_id": manuscript_id, "role": role,
                "operation_key": operation_key, "estimated_cost_usd": estimate,
                "actual_cost_usd": None, "status": "reserved", "created_at": datetime.now().isoformat(),
            })
            return {"reserved": True, "limit_usd": limit, "spent_usd": spent, "reserved_usd": reserved + estimate}

    async def settle_cost(self, reservation_id, actual_cost_usd):
        async with self._cost_lock:
            reservation = next((row for row in self._data["cost_reservations"] if row.get("id") == reservation_id), None)
            if not reservation or reservation.get("status") != "reserved":
                return
            manuscript = next(row for row in self._data["manuscripts"] if row.get("id") == reservation["manuscript_id"])
            estimate = float(reservation["estimated_cost_usd"])
            manuscript["cost_reserved_usd"] = max(0, float(manuscript.get("cost_reserved_usd") or 0) - estimate)
            manuscript["cost_spent_usd"] = float(manuscript.get("cost_spent_usd") or 0) + max(0, float(actual_cost_usd))
            reservation.update({"actual_cost_usd": max(0, float(actual_cost_usd)), "status": "completed"})

    async def release_cost(self, reservation_id):
        async with self._cost_lock:
            reservation = next((row for row in self._data["cost_reservations"] if row.get("id") == reservation_id), None)
            if not reservation or reservation.get("status") != "reserved":
                return
            manuscript = next(row for row in self._data["manuscripts"] if row.get("id") == reservation["manuscript_id"])
            manuscript["cost_reserved_usd"] = max(0, float(manuscript.get("cost_reserved_usd") or 0) - float(reservation["estimated_cost_usd"]))
            reservation["status"] = "released"

    async def cleanup_stale_cost_reservations(self):
        return 0


def get_memory_db() -> _MemoryDb:
    return _MemoryDb()
