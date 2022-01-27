try:
    # Linux expects the latest package version of 3.35.4 (as of pysqlite-binary 0.4.6)
    import pysqlite3 as sqlite3
except ModuleNotFoundError:
    # MacOS has latest brew version of 3.35.5 (as of 2021-06-20).
    # Windows builds use the official Python 3.10.0 builds and bundled version of 3.35.5.
    import sqlite3 # type: ignore[no-redef]

from typing import Any, cast, Collection, List, Optional, Sequence, Tuple, Type, TypeVar

from bitcoinx import base58_decode_check, PublicKey

from .sqlite_support import SQLITE_EXPR_TREE_DEPTH, SQLITE_MAX_VARS

from ..constants import DerivationType, pack_derivation_path
from ..types import KeyInstanceDataBIP32SubPath, KeyInstanceDataHash, KeyInstanceDataTypes, \
    KeyInstanceDataPrivateKey

T = TypeVar('T')
T2 = TypeVar('T2')


def create_derivation_data2(derivation_type: DerivationType,
        derivation_data: KeyInstanceDataTypes) -> bytes:
    if derivation_type == DerivationType.BIP32_SUBPATH:
        derivation_path = cast(KeyInstanceDataBIP32SubPath, derivation_data)["subpath"]
        return pack_derivation_path(derivation_path)
    elif derivation_type == DerivationType.PRIVATE_KEY:
        public_key_bytes = bytes.fromhex(cast(KeyInstanceDataPrivateKey, derivation_data)['pub'])
        # Ensure all public keys are canonically encoded in the compressed form.
        if len(public_key_bytes) != 33:
            public_key_bytes = PublicKey.from_bytes(public_key_bytes).to_bytes(compressed=True)
        return public_key_bytes
    elif derivation_type in (DerivationType.PUBLIC_KEY_HASH, DerivationType.SCRIPT_HASH):
        # We manually extract this rather than using the `bitcoinx.Address` class as we do
        # not care about the coin as that is implicit in the wallet.
        derivation_data_hash = cast(KeyInstanceDataHash, derivation_data)
        raw = cast(bytes, base58_decode_check(derivation_data_hash['hash']))
        if len(raw) != 21:
            raise ValueError(f'invalid address: {derivation_data_hash["hash"]}')
        return raw[1:]
    raise NotImplementedError()


def collect_results(result_type: Type[T], cursor: sqlite3.Cursor, results: List[T]) -> None:
    """
    Collect the results of a query and extend a result list with correct typing.
    """
    rows = cursor.fetchall()
    cursor.close()
    results.extend(result_type(*row) for row in rows)


def flag_clause(column: str, flags: Optional[T], mask: Optional[T]) -> Tuple[str, List[T]]:
    if flags is None:
        if mask is None:
            return "", []
        return f"({column} & ?) != 0", [mask]

    if mask is None:
        return f"({column} & ?) != 0", [flags]

    return f"({column} & ?) == ?", [mask, flags]


def read_rows_by_id(return_type: Type[T], db: sqlite3.Connection, sql: str, params: Sequence[Any],
        ids: Sequence[T2]) -> List[T]:
    """
    Batch read rows as constrained by database limitations.
    """
    results: List[T] = []
    batch_size = SQLITE_MAX_VARS - len(params)
    remaining_ids = ids
    while len(remaining_ids):
        batch_ids = remaining_ids[:batch_size]
        sql = sql.format(",".join("?" for k in batch_ids))
        # NOTE(typing) the sequence type does not provide an addition operator hence typing ignored.
        cursor = db.execute(sql, params + batch_ids) # type: ignore
        rows = cursor.fetchall()
        cursor.close()
        # Skip copying/conversion for standard types.
        if len(rows):
            if return_type is bytes:
                assert len(rows[0]) == 1 and type(rows[0][0]) is return_type
                results.extend(row[0] for row in rows)
            else:
                results.extend(return_type(*row) for row in rows)
        remaining_ids = remaining_ids[batch_size:]
    return results


def read_rows_by_ids(return_type: Type[T], db: sqlite3.Connection, sql: str, sql_condition: str,
        sql_values: List[Any], ids: Sequence[Collection[T2]]) -> List[T]:
    """
    Read rows in batches as constrained by database limitations.
    """
    batch_size = min(SQLITE_MAX_VARS, SQLITE_EXPR_TREE_DEPTH) // 2 - len(sql_values)
    results: List[T] = []
    remaining_ids = ids
    while len(remaining_ids):
        batch = remaining_ids[:batch_size]
        batch_values: List[Any] = list(sql_values)
        for batch_entry in batch:
            batch_values.extend(batch_entry)
        conditions = [ sql_condition ] * len(batch)
        batch_query = (sql +" WHERE "+ " OR ".join(conditions))
        cursor = db.execute(batch_query, batch_values)
        results.extend(return_type(*row) for row in cursor.fetchall())
        cursor.close()
        remaining_ids = remaining_ids[batch_size:]
    return results


# TODO(ideal) In an ideal world we would pass in a row factory and a return type, or use the typing
#   stuff to use them. For instance, if fields in the return type are `IntFlag` structures they are
#   not treated the same in their integer form as they would be if they were cast to the structure.
def execute_sql_by_id(db: sqlite3.Connection, sql: str,
        sql_values: List[Any], ids: Sequence[T2], return_type: Optional[Type[T]]=None) \
            -> Tuple[int, List[T]]:
    """
    Update, delete or whatever rows in batches as constrained by database limitations.

    If the update statement returns values via `RETURNING`, specify a return type. However, it has
    been observed that sometimes rows will be updated and returned, where `rowcount` is set to
    zero. So it is better to check the count of the updates returned values, than rely on the
    `rowcount` field.
    """
    batch_size = SQLITE_MAX_VARS - len(sql_values)
    rows_updated = 0
    remaining_ids = ids
    rows: List[T] = []
    while len(remaining_ids):
        batch_ids = remaining_ids[:batch_size]
        sql = sql.format(",".join("?" for k in batch_ids))
        # NOTE(typing) Cannot add a sequence to a list.
        cursor = db.execute(sql, sql_values + batch_ids) # type: ignore
        if return_type is not None:
            rows.extend(return_type(*row) for row in cursor.fetchall())
        rows_updated += cursor.rowcount
        cursor.close()
        remaining_ids = remaining_ids[batch_size:]
    return rows_updated, rows


def bulk_insert_returning(return_type: Type[T], db: sqlite3.Connection, sql_prefix: str,
        sql_suffix: str, insert_rows: Sequence[Collection[T2]]) -> List[T]:
    """
    Do a bulk insert in a way where we get the primary key value back.

    sql_prefix expected value `INSERT INTO MyTable (column1, column2) VALUES `
    sql_suffix expected value `RETURNING key_column, column1, column2`

    SQLite does not guarantee the order of the returned values, so it cannot be used to just
    return the assigned primary key value for each given row. Instead the simplest approach is
    to just return the whole row and give it back to the calling logic to use in place of the
    source row data that went in.

    It is the reponsibility of the caller to ensure the RETURNING column order provided in
    `sql_suffix` matches the number of elements, and order, of the type to be returned
    `return_type`.
    """
    row_size = len(insert_rows[0])
    rows_per_batch = int(SQLITE_MAX_VARS // row_size)

    value_parameter_text = "("+ ",".join(["?"] * row_size) +")"
    next_row_index = 0
    final_rows: List[T] = []
    while next_row_index < len(insert_rows):
        batch_row_count = min(rows_per_batch, len(insert_rows)-next_row_index)
        batch_values: List[Any] = []
        values_text = ""
        for i in range(next_row_index, next_row_index + batch_row_count):
            if len(values_text):
                values_text += ","
            values_text += value_parameter_text
            batch_values.extend(insert_rows[i])

        sql_completed = f"{sql_prefix} {values_text} {sql_suffix}"
        for inserted_row in db.execute(sql_completed, batch_values):
            final_rows.append(return_type(*inserted_row))

        next_row_index += batch_row_count
    return final_rows


def update_rows_by_ids(db: sqlite3.Connection, sql: str, sql_id_expression: str,
        sql_values: List[Any], ids: Sequence[Collection[T]],
        sql_where_expression: Optional[str]=None) -> int:
    """
    Update rows in batches as constrained by database limitations.

    This does not yet support `RETURNING`.
    """
    batch_size = min(SQLITE_MAX_VARS, SQLITE_EXPR_TREE_DEPTH) // 2 - len(sql_values)
    rows_updated = 0
    remaining_ids = ids
    while len(remaining_ids):
        batch_ids = remaining_ids[:batch_size]
        batch_values: List[Any] = sql_values[:]
        for batch_entry in batch_ids:
            batch_values.extend(batch_entry)
        id_sql_expressions = [ sql_id_expression ] * len(batch_ids)
        sql_completed = sql +" WHERE "
        sql_completed_id_expression = " OR ".join(id_sql_expressions)
        if sql_where_expression:
            sql_completed += f"{sql_where_expression} AND ({sql_completed_id_expression})"
        else:
            sql_completed += sql_completed_id_expression
        cursor = db.execute(sql_completed, batch_values)
        rows_updated += cursor.rowcount
        cursor.close()
        remaining_ids = remaining_ids[batch_size:]
    return rows_updated
