"""
snowflake_connector.py
----------------------
Manages the Snowflake connection lifecycle and exposes a single helper for
executing read-only SQL queries.  All writes are intentionally blocked.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import snowflake.connector
from snowflake.connector import SnowflakeConnection
from snowflake.connector.errors import DatabaseError, OperationalError, ProgrammingError

from config import snowflake_config

logger = logging.getLogger(__name__)

# SQL verbs that are never permitted through this module.
_FORBIDDEN_VERBS = frozenset(
    ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "MERGE", "REPLACE"]
)


def _guard_read_only(sql: str) -> None:
    """Raise ValueError if the SQL statement is not a SELECT / WITH / SHOW / DESCRIBE."""
    first_token = sql.strip().split()[0].upper()
    if first_token in _FORBIDDEN_VERBS:
        raise ValueError(
            f"Write operations are not permitted. Blocked statement starting with: {first_token}"
        )


def get_connection() -> SnowflakeConnection:
    """
    Open and return an authenticated Snowflake connection.

    Returns
    -------
    SnowflakeConnection
        An open connection to the configured Snowflake account.

    Raises
    ------
    OperationalError
        If the connection cannot be established (bad credentials, network, etc.).
    """
    try:
        conn = snowflake.connector.connect(
            account=snowflake_config.account,
            user=snowflake_config.user,
            password=snowflake_config.password,
            database=snowflake_config.database,
            schema=snowflake_config.schema,
            warehouse=snowflake_config.warehouse,
            role=snowflake_config.role,
            session_parameters={"QUERY_TAG": "langchain-intelligence-agent"},
        )
        logger.info(
            "Snowflake connection established — account=%s database=%s schema=%s",
            snowflake_config.account,
            snowflake_config.database,
            snowflake_config.schema,
        )
        return conn
    except OperationalError as exc:
        logger.error("Failed to connect to Snowflake: %s", exc)
        raise


def execute_query(sql: str, max_rows: int = 1000) -> pd.DataFrame:
    """
    Execute a read-only SQL statement and return results as a DataFrame.

    Parameters
    ----------
    sql : str
        A SELECT or WITH … SELECT statement to execute.
    max_rows : int
        Maximum number of rows to fetch (safety cap, default 1 000).

    Returns
    -------
    pd.DataFrame
        Query results.  Empty DataFrame if no rows matched.

    Raises
    ------
    ValueError
        If a non-SELECT statement is attempted.
    DatabaseError / ProgrammingError
        On SQL syntax errors or Snowflake execution failures.
    """
    _guard_read_only(sql)

    logger.debug("Executing SQL:\n%s", sql)

    conn: SnowflakeConnection | None = None
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchmany(max_rows)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        df = pd.DataFrame(rows, columns=columns)
        logger.info("Query returned %d rows, %d columns.", len(df), len(df.columns))
        return df
    except ProgrammingError as exc:
        logger.error("SQL programming error: %s\nSQL was:\n%s", exc, sql)
        raise
    except DatabaseError as exc:
        logger.error("Snowflake database error: %s", exc)
        raise
    finally:
        if conn:
            conn.close()


def execute_query_as_string(sql: str, max_rows: int = 200) -> str:
    """
    Execute a query and return the results formatted as a markdown table string.

    Parameters
    ----------
    sql : str
        SQL to execute.
    max_rows : int
        Row limit passed to execute_query.

    Returns
    -------
    str
        Markdown-formatted table, or an error message prefixed with "ERROR:".
    """
    try:
        df = execute_query(sql, max_rows=max_rows)
        if df.empty:
            return "Query executed successfully but returned no rows."
        return df.to_markdown(index=False)
    except ValueError as exc:
        return f"ERROR: {exc}"
    except (DatabaseError, ProgrammingError) as exc:
        return f"ERROR executing SQL: {exc}"
    except Exception as exc:  # pylint: disable=broad-except
        return f"ERROR: Unexpected error — {exc}"


def test_connection() -> bool:
    """
    Verify that the Snowflake connection is reachable.

    Returns
    -------
    bool
        True if a simple SELECT 1 succeeds, False otherwise.
    """
    try:
        df = execute_query("SELECT 1 AS ping")
        return not df.empty
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Connection test failed: %s", exc)
        return False
