
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_voyageai import VoyageAIEmbeddings
from langchain_chroma import Chroma
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import asyncio
import json
from datetime import datetime
from anthropic import Anthropic
from ddgs import DDGS
from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession

def run_async(coroutine):
    loop = asyncio.new_event_loop()

    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()

#conf
BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "data" / "it_sector.txt"
CHROMA_PATH = BASE_DIR / "chroma_db"
MCP_SERVER_URL = "http://localhost:3000/mcp"

load_dotenv(BASE_DIR / ".env")


#vogage
def get_embeddings():

    api_key = os.getenv("VOYAGE_API_KEY")

    if not api_key:
        raise ValueError(
            "VOYAGE_API_KEY was not found in the .env file."
        )

    embeddings = VoyageAIEmbeddings(
        model="voyage-3.5",
        voyage_api_key=api_key
    )

    return embeddings

#load doc
def load_documents():

    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"Knowledge file not found: {DATA_PATH}"
        )

    with open(DATA_PATH, "r", encoding="utf-8") as file:
        content = file.read()

    if not content.strip():
        raise ValueError("The knowledge file is empty.")

    documents = [
        Document(
            page_content=content,
            metadata={
                "source": "it_sector.txt"
            }
        )
    ]

    return documents

#slit doc in chunks
def split_documents(documents):

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n\n", "\n", ". ", " ", ""]
    )

    chunks = text_splitter.split_documents(documents)

    return chunks


#create or load database chroma
def create_vector_store():

    embeddings = get_embeddings()

    documents = load_documents()

    chunks = split_documents(documents)

    vector_store = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name="it_support_knowledge",
        persist_directory=str(CHROMA_PATH)
    )

    return vector_store

#load existing database or create new one
def load_vector_store():

    embeddings = get_embeddings()

    if not CHROMA_PATH.exists():
        return create_vector_store()

    vector_store = Chroma(
        collection_name="it_support_knowledge",
        embedding_function=embeddings,
        persist_directory=str(CHROMA_PATH)
    )

    if vector_store._collection.count() == 0:
        return create_vector_store()

    return vector_store

#retrieve relevant information based on the question
def retrieve_information(question, k=3):

    vector_store = load_vector_store()

    results = vector_store.similarity_search(
        question,
        k=k
    )

    return results

#context for the question
def get_context(question):

    documents = retrieve_information(question)

    context = "\n\n".join(
        document.page_content
        for document in documents
    )

    return context


#initialize LLM

def get_llm():

    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY was not found in the .env file."
        )

    llm = ChatAnthropic(
        model="claude-sonnet-4-6",
        anthropic_api_key=api_key,
        max_tokens=1024
    )

    return llm

#generate answer to the question using the context and LLM
def answer_question(question):

    context = get_context(question)

    llm = get_llm()

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            """
            You are an IT Support Assistant.

            Answer the user's questions using the
            provided IT support knowledge.

            Instructions:
            - Use the context to answer.
            - Do not invent technical information.
            - If the answer is not in the context,
              clearly say that the knowledge base
              does not contain enough information.
            - Give clear and helpful instructions.
            - Respond in the same language as the user.

            CONTEXT:
            {context}
            """
        ),
        (
            "human",
            "{question}"
        )
    ])

    chain = prompt | llm | StrOutputParser()

    response = chain.invoke({
        "context": context,
        "question": question
    })

    return response

#test the implementation rag
if __name__ == "__main__":

    print("\nInitializing IT Support Chatbot...\n")

    question = input("Enter your IT support question: ")

    try:
        response = answer_question(question)

        print("\nIT Support Assistant:\n")
        print(response)

    except Exception as error:
        print(f"\nError: {error}")



#web search tool
def web_search(query: str) -> str:
    """Search the web for IT troubleshooting solutions."""

    try:
        with DDGS() as ddgs:
            results = list(
                ddgs.text(query, max_results=5)
            )

        if not results:
            return "No web results found."

        return "\n".join([
            f"Title: {r.get('title')}\n"
            f"URL: {r.get('href')}\n"
            f"Description: {r.get('body')}"
            for r in results
        ])

    except Exception as error:
        return f"Web search error: {error}"


#datetime current 
def get_current_datetime() -> str:
    """Get the current local date and time."""

    return datetime.now().astimezone().strftime(
        "%Y-%m-%d %H:%M:%S %Z"
    )


#mcp client
async def mcp_call(function):

    async with streamable_http_client(
        MCP_SERVER_URL
    ) as (read_stream, write_stream):

        async with ClientSession(
            read_stream,
            write_stream
        ) as session:

            await session.initialize()

            return await function(session)


# Get available MCP tools
async def get_mcp_tools():

    async def list_tools(session):
        return await session.list_tools()

    result = await mcp_call(list_tools)

    return result.tools


# Execute an MCP tool
async def execute_mcp_tool(name, arguments):

    async def call_tool(session):
        return await session.call_tool(
            name,
            arguments
        )

    result = await mcp_call(call_tool)

    return "\n".join(
        item.text
        for item in result.content
        if hasattr(item, "text")
    )


#claude tool calling
def run_assistant(question, chat_history=None):

    api_key = os.getenv("ANTHROPIC_API_KEY")

    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY missing.")

    client = Anthropic(api_key=api_key)

    # Retrieve context from our existing RAG
    context = get_context(question) or ""

    # Obtain tools from MCP Server
    mcp_tools = run_async(get_mcp_tools())

    tools = [
        {
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": tool.input_schema
        }
        for tool in mcp_tools
    ]

    # Additional tools
    tools.extend([
        {
            "name": "web_search",
            "description": "Search the internet for IT solutions.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"}
                },
                "required": ["query"]
            }
        },
        {
            "name": "get_current_datetime",
            "description": "Get current local date and time.",
            "input_schema": {
                "type": "object",
                "properties": {}
            }
        }
    ])

    messages = list(chat_history or [])
    messages.append({
        "role": "user",
        "content": question
    })

    system_prompt = f"""
    You are an IT Helpdesk Assistant.

    Use the following IT knowledge base to answer questions:

    {context}

    RULES:
    - Use RAG context for common IT support questions.
    - Use web_search for latest information or when
      additional online troubleshooting is requested.
    - Use get_current_datetime when asked about date or time.
    - Use create_support_ticket when the user requests a ticket.
    - Ask for missing employee or issue information before
      creating a ticket.
    - Use check_ticket_status for ticket status requests.
    - Never invent ticket IDs or ticket statuses.
    - Respond in the user's language.
    - Give clear and helpful answers.
    """

    for _ in range(6):

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            system=system_prompt,
            messages=messages,
            tools=tools
        )

        if response.stop_reason != "tool_use":
            return "\n".join(
                block.text
                for block in response.content
                if block.type == "text"
            )

        messages.append({
            "role": "assistant",
            "content": response.content
        })

        tool_results = []

        for block in response.content:

            if block.type != "tool_use":
                continue

            name = block.name
            arguments = block.input

            try:
                if name in [
                    "create_support_ticket",
                    "check_ticket_status"
                ]:
                    result = run_async(
                        execute_mcp_tool(name, arguments)
                    )

                elif name == "web_search":
                    result = web_search(
                        arguments["query"]
                    )

                elif name == "get_current_datetime":
                    result = get_current_datetime()

                else:
                    result = "Unknown tool."

            except Exception as error:
                result = f"Tool execution error: {error}"

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(result)
            })

        messages.append({
            "role": "user",
            "content": tool_results
        })

    return "Maximum tool calls reached. Please try again."

