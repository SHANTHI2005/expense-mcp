"""Chat client: local Ollama model + the expense MCP server.

Usage:  python client.py
Needs Ollama running with the model pulled: ollama pull llama3.2:3b
"""
import asyncio
import json
import sys
from datetime import date

import ollama
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

MODEL = "llama3.2:3b"
MAX_TOOL_ROUNDS = 5


def to_ollama_tools(mcp_tools):
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema,
            },
        }
        for t in mcp_tools
    ]


def result_text(result) -> str:
    if result.structuredContent:
        return json.dumps(result.structuredContent)
    return "\n".join(c.text for c in result.content if hasattr(c, "text"))


async def chat_turn(session, messages, tools):
    """Let the model call tools until it gives a plain answer."""
    for _ in range(MAX_TOOL_ROUNDS):
        response = ollama.chat(model=MODEL, messages=messages, tools=tools)
        messages.append(response.message)

        if not response.message.tool_calls:
            return response.message.content

        for call in response.message.tool_calls:
            name, args = call.function.name, call.function.arguments
            print(f"  -> {name}({args})")
            result = await session.call_tool(name, args)
            text = result_text(result)
            if result.isError:
                text = f"Error: {text}"
            messages.append({"role": "tool", "content": text, "tool_name": name})

    return "Stopped after too many tool calls. Try rephrasing."


async def main():
    params = StdioServerParameters(command=sys.executable, args=["server.py"])

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            mcp_tools = (await session.list_tools()).tools
            tools = to_ollama_tools(mcp_tools)
            print("Connected. Tools:", ", ".join(t.name for t in mcp_tools))
            print("Type 'exit' to quit.\n")

            messages = [{
                "role": "system",
                "content": (
                    "You are an expense tracking assistant. Amounts are in Indian rupees. "
                    f"Today is {date.today().isoformat()}. "
                    "Use the tools to add, list, total or delete expenses. "
                    "Answer briefly using the tool results."
                ),
            }]

            while True:
                user_input = input("You: ").strip()
                if user_input.lower() in {"exit", "quit"}:
                    break
                if not user_input:
                    continue
                messages.append({"role": "user", "content": user_input})
                try:
                    answer = await chat_turn(session, messages, tools)
                except ollama.ResponseError as e:
                    answer = f"Ollama error: {e}. Is the model pulled?"
                except ConnectionError:
                    answer = "Cannot reach Ollama. Open the Ollama app or run 'ollama serve'."
                print("AI:", answer, "\n")


if __name__ == "__main__":
    asyncio.run(main())
