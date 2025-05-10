import os
import requests
from langchain.agents import initialize_agent, AgentType
from langchain.tools import Tool
from langchain.llms import LlamaCpp

def vector_search_tool(q: str) -> dict:
    res = requests.post("http://localhost:8000/match/skus", json={"skus": [q]})
    return res.json()

tools = [
    Tool(
        name="CatalogVectorSearch",
        func=vector_search_tool,
        description="Use to look up a product token and get possible SKU matches with confidence."
    )
]

llm = LlamaCpp(
    model_path=os.getenv("LCPP_MODEL_PATH"),
    n_ctx=2048,
    temperature=0
)

agent = initialize_agent(
    tools,
    llm,
    agent_type=AgentType.OPENAI_FUNCTIONS,
    system_message="""
    You are an order-entry assistant. Given a raw token, call the tool and choose the best match.
    Return JSON: {"sku": "...", "status": "CONFIRMED|AMBIGUOUS"}
    """
)
