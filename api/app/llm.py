import os
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

DEFAULT_MODEL = "mistralai/mistral-small-3.2-24b-instruct"

def get_llm(model_name: str = DEFAULT_MODEL):
    return ChatOpenAI(
        model=model_name,
        openai_api_key=OPENROUTER_API_KEY,
        openai_api_base=OPENROUTER_BASE_URL,
        temperature=0.3,
        max_tokens=1024,
    )

def get_rag_agent(tools=[]):
    llm = get_llm()
    system_message = """
    You are a helpful assistant that answers user questions based on provided Google Sheets context.
    Use the context strictly to answer questions. 
    If the context is insufficient, say "I don't know" instead of hallucinating.
    """
    llm = llm.with_config(system_message=system_message)
    return create_react_agent(llm, tools=tools)