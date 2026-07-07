"""Execute multi-statement SQL scripts under Alembic with the asyncpg driver.

asyncpg sends statements through the extended (prepared-statement) protocol,
which rejects a string containing multiple commands
("cannot insert multiple commands into a prepared statement"). Migrations that
replay a whole ``.sql`` file (the baseline + the reconciliation migrations) must
therefore split the script and execute one statement at a time.

The splitter is line-oriented and dollar-quote aware: ``$$``-delimited blocks
(functions, ``DO`` blocks, partition loops) are kept intact, and a statement is
only terminated when a line ends with ``;`` while not inside such a block. All
project SQL files use plain ``$$`` (no named ``$tag$`` quotes), which this
handles correctly.
"""

from __future__ import annotations

from alembic import op


def split_sql_statements(sql: str) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    in_dollar = False
    for line in sql.splitlines():
        # An odd number of `$$` on a line toggles in/out of a dollar-quoted body;
        # an even number (e.g. a self-contained `DO $$ ... $$` on one line) nets
        # to no change.
        if line.count("$$") % 2 == 1:
            in_dollar = not in_dollar
        buf.append(line)
        if not in_dollar and line.rstrip().endswith(";"):
            out.append("\n".join(buf))
            buf = []
    if buf:
        out.append("\n".join(buf))
    # Drop empty / comment-only fragments.
    return [s for s in out if _has_executable_sql(s)]


def _has_executable_sql(stmt: str) -> bool:
    for line in stmt.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            return True
    return False


def exec_sql_script(sql: str) -> None:
    """Split a multi-statement SQL script and execute each statement via Alembic.

    Uses ``exec_driver_sql`` (raw passthrough to the driver) rather than
    ``op.execute`` so that SQLAlchemy does NOT interpret ``:name`` sequences as
    bind parameters — the SQL files embed JSON like ``"power_rating_w":450`` that
    would otherwise be misread as bind parameters.
    """
    bind = op.get_bind()
    for stmt in split_sql_statements(sql):
        bind.exec_driver_sql(stmt)
