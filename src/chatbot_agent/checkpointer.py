from langgraph.checkpoint.postgres import PostgresSaver
from db.engine import engine

DB_URI = str(engine.url)

checkpointer = PostgresSaver.from_conn_string(DB_URI)

checkpointer.setup()