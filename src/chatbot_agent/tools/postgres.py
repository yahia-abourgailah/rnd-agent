from langchain_core.tools import tool
from langchain_community.utilities import SQLDatabase

from db.engine import engine

db = SQLDatabase(engine)


@tool
def query_database(query: str) -> str:
    """
    Execute a SQL query against the PostgreSQL database.
    """
    try:
      return db.run(query)
    except Exception as e:
     return f"Database error: {e}"
   
    
