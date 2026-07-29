from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

# Load environment variables from .env
load_dotenv()

# Initialize the language model
llm = init_chat_model(
    model="gemma-4",
    model_provider="openai",
)