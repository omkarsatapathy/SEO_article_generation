from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool


def get_pool(db_url: str) -> ConnectionPool:
    """Create and return a reusable psycopg connection pool."""
    return ConnectionPool(
        conninfo=db_url,
        max_size=10,
        kwargs={"autocommit": True},
    )


def get_checkpointer(db_url: str) -> PostgresSaver:
    """
    Build a PostgresSaver checkpointer backed by a connection pool.

    Calls checkpointer.setup() to ensure the LangGraph checkpoint tables
    (checkpoints, checkpoint_writes, checkpoint_blobs) exist before returning.
    """
    pool = get_pool(db_url)
    with pool.connection() as conn:
        checkpointer = PostgresSaver(conn)
        checkpointer.setup()
    return checkpointer
