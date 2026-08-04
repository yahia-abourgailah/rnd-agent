from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver

from chatbot_agent.graph import build_graph
from config.settings import settings
import uuid




# ---------- Request / Response Models ----------

class ChatRequest(BaseModel):
  
    message: str


class ChatResponse(BaseModel):
    response: str


# ---------- FastAPI Lifespan ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    checkpoint_db_url = settings.database_url.replace(
        "postgresql+psycopg://",
        "postgresql://",
    )

    with PostgresSaver.from_conn_string(checkpoint_db_url) as checkpointer:
        app.state.graph = build_graph(checkpointer)
        yield


app = FastAPI(
    title="Real Estate Chatbot",
    lifespan=lifespan,
)


# ---------- Routes ----------

@app.get("/")
def root():
    return {"message": "Real Estate Chatbot API is running!"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    print("Request received")

    config = {
        "configurable": {
            "thread_id":str(uuid.uuid4())
        }
    }

    print("Invoking graph...")

    result = app.state.graph.invoke(
        {
            "messages": [
                HumanMessage(content=request.message)
            ]
        },
        config=config,
    )

    print("Graph finished")

    return ChatResponse(
        response=result["messages"][-1].content
    )