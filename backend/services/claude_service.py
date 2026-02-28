"""
Claude AI service: system prompt construction, tool use, streaming, context management.
"""
import json
from typing import AsyncIterator, List, Dict, Optional
import anthropic

from ..config import config
from .search_service import web_search, format_search_results
from .calculations import (
    gross_yield, net_yield, development_margin,
    calculate_irr, calculate_npv, loan_serviceability, stamp_duty_estimate,
)

_client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

SYSTEM_PROMPT_BASE = """You are a strategic property development advisor and project assistant. \
You help with strategic planning, financial feasibility, planning and zoning analysis, \
community benefit assessment, market research, and investment evaluation for property development projects.

Your communication style is:
- Direct and practical - focus on actionable insights
- Financially literate - comfortable with development economics, IRR, yields, margins
- Aware of planning frameworks, community obligations, and stakeholder dynamics
- Able to switch between high-level strategy and detailed financial analysis
- Conversational when the user is thinking out loud; structured when producing analysis

When performing financial calculations, use the provided calculation tools for precision. \
When you need current market data, planning information, or comparable projects, use the web_search tool.

Always cite which project documents you're drawing on when referencing uploaded materials."""

TOOLS = [
    {
        "name": "web_search",
        "description": "Search the web for current property market data, planning information, comparable projects, interest rates, or any other real-world information needed for the analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query. Be specific - include location, property type, and what you're looking for.",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "calculate_yield",
        "description": "Calculate gross and net rental yield for a property.",
        "input_schema": {
            "type": "object",
            "properties": {
                "purchase_price": {"type": "number", "description": "Purchase or valuation price in dollars"},
                "annual_rent": {"type": "number", "description": "Annual rental income in dollars"},
                "annual_costs": {"type": "number", "description": "Annual operating costs (optional - for net yield)", "default": 0},
            },
            "required": ["purchase_price", "annual_rent"],
        },
    },
    {
        "name": "calculate_development_margin",
        "description": "Calculate development margin and return on cost for a development project.",
        "input_schema": {
            "type": "object",
            "properties": {
                "gross_realisation": {"type": "number", "description": "Total end value / gross sales revenue"},
                "total_development_cost": {"type": "number", "description": "All-in development cost including land, construction, finance, holding costs"},
            },
            "required": ["gross_realisation", "total_development_cost"],
        },
    },
    {
        "name": "calculate_irr",
        "description": "Calculate Internal Rate of Return (IRR) from a series of cash flows.",
        "input_schema": {
            "type": "object",
            "properties": {
                "cash_flows": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "List of cash flows by period. First value is typically negative (investment). E.g. [-1000000, 200000, 300000, 800000]",
                },
                "discount_rate": {"type": "number", "description": "Discount rate for NPV (optional, as decimal e.g. 0.08 for 8%)"},
            },
            "required": ["cash_flows"],
        },
    },
    {
        "name": "calculate_loan",
        "description": "Calculate loan repayments and serviceability metrics.",
        "input_schema": {
            "type": "object",
            "properties": {
                "loan_amount": {"type": "number"},
                "annual_interest_rate": {"type": "number", "description": "As decimal, e.g. 0.065 for 6.5%"},
                "loan_term_years": {"type": "number"},
                "annual_income": {"type": "number", "description": "Annual income for serviceability check"},
            },
            "required": ["loan_amount", "annual_interest_rate", "loan_term_years"],
        },
    },
    {
        "name": "estimate_stamp_duty",
        "description": "Estimate stamp duty for an Australian property purchase.",
        "input_schema": {
            "type": "object",
            "properties": {
                "purchase_price": {"type": "number"},
                "state": {"type": "string", "description": "Australian state code: NSW, VIC, QLD, etc.", "default": "NSW"},
            },
            "required": ["purchase_price"],
        },
    },
]


async def _execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute a tool call and return JSON string result."""
    try:
        if tool_name == "web_search":
            results = await web_search(tool_input["query"])
            return format_search_results(results)

        elif tool_name == "calculate_yield":
            result = gross_yield(
                tool_input["purchase_price"],
                tool_input["annual_rent"],
            )
            if tool_input.get("annual_costs", 0) > 0:
                net = net_yield(
                    tool_input["purchase_price"],
                    tool_input["annual_rent"],
                    tool_input["annual_costs"],
                )
                result.update(net)
            return json.dumps(result, indent=2)

        elif tool_name == "calculate_development_margin":
            result = development_margin(
                tool_input["gross_realisation"],
                tool_input["total_development_cost"],
            )
            return json.dumps(result, indent=2)

        elif tool_name == "calculate_irr":
            result = calculate_irr(tool_input["cash_flows"])
            if tool_input.get("discount_rate"):
                npv = calculate_npv(tool_input["discount_rate"], tool_input["cash_flows"])
                result.update(npv)
            return json.dumps(result, indent=2)

        elif tool_name == "calculate_loan":
            result = loan_serviceability(
                tool_input["loan_amount"],
                tool_input["annual_interest_rate"],
                int(tool_input["loan_term_years"]),
                tool_input.get("annual_income", 0),
            )
            return json.dumps(result, indent=2)

        elif tool_name == "estimate_stamp_duty":
            result = stamp_duty_estimate(
                tool_input["purchase_price"],
                tool_input.get("state", "NSW"),
            )
            return json.dumps(result, indent=2)

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        return json.dumps({"error": str(e)})


def _build_system_prompt(
    project_name: str,
    project_description: str,
    doc_chunks: List[Dict],
    summary: Optional[str],
) -> str:
    parts = [SYSTEM_PROMPT_BASE]
    parts.append(f"\n\n## Current Project: {project_name}")
    if project_description:
        parts.append(f"\n{project_description}")

    if doc_chunks:
        parts.append("\n\n## Relevant Project Documents\n")
        for chunk in doc_chunks:
            meta = chunk.get("metadata", {})
            source = meta.get("source", "")
            doc_id = meta.get("doc_id", "")
            relevance = chunk.get("relevance", 0)
            parts.append(f"[Source: {source}, relevance: {relevance:.2f}]\n{chunk['text']}\n")

    if summary:
        parts.append(f"\n\n## Earlier Discussion Summary\n{summary}")

    return "".join(parts)


async def stream_chat(
    project_name: str,
    project_description: str,
    messages: List[Dict],  # [{role, content}] - full history for context
    doc_chunks: List[Dict],
    summary: Optional[str],
) -> AsyncIterator[str]:
    """
    Stream a chat response as Server-Sent Events.
    Handles tool use (web search, calculations) transparently.
    Yields SSE-formatted strings.
    """
    system_prompt = _build_system_prompt(
        project_name, project_description, doc_chunks, summary
    )

    # Convert messages to Anthropic format
    anthropic_messages = []
    for m in messages:
        anthropic_messages.append({"role": m["role"], "content": m["content"]})

    # Agentic loop: keep running until Claude returns stop_reason="end_turn"
    max_iterations = 5  # prevent infinite loops
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        full_response = ""
        tool_uses = []
        stop_reason = None

        async with _client.messages.stream(
            model=config.CLAUDE_MODEL,
            max_tokens=4096,
            system=system_prompt,
            messages=anthropic_messages,
            tools=TOOLS,
        ) as stream:
            current_tool = None
            current_tool_input = ""

            async for event in stream:
                event_type = type(event).__name__

                if event_type == "RawContentBlockStartEvent":
                    block = event.content_block
                    if block.type == "text":
                        pass  # text coming
                    elif block.type == "tool_use":
                        current_tool = {"id": block.id, "name": block.name}
                        current_tool_input = ""
                        yield f"data: {json.dumps({'type': 'tool_start', 'tool': block.name})}\n\n"

                elif event_type == "RawContentBlockDeltaEvent":
                    delta = event.delta
                    if hasattr(delta, "text"):
                        full_response += delta.text
                        yield f"data: {json.dumps({'type': 'text', 'content': delta.text})}\n\n"
                    elif hasattr(delta, "partial_json"):
                        current_tool_input += delta.partial_json

                elif event_type == "RawContentBlockStopEvent":
                    if current_tool:
                        try:
                            parsed_input = json.loads(current_tool_input) if current_tool_input else {}
                        except json.JSONDecodeError:
                            parsed_input = {}
                        tool_uses.append({
                            "id": current_tool["id"],
                            "name": current_tool["name"],
                            "input": parsed_input,
                        })
                        current_tool = None
                        current_tool_input = ""

                elif event_type == "RawMessageStopEvent":
                    stop_reason = event.message.stop_reason

        # If no tool use, we're done
        if not tool_uses or stop_reason == "end_turn":
            break

        # Execute tools and continue the conversation
        tool_result_content = []
        for tool_use in tool_uses:
            yield f"data: {json.dumps({'type': 'tool_running', 'tool': tool_use['name'], 'query': tool_use['input'].get('query', '')})}\n\n"
            result = await _execute_tool(tool_use["name"], tool_use["input"])
            tool_result_content.append({
                "type": "tool_result",
                "tool_use_id": tool_use["id"],
                "content": result,
            })
            yield f"data: {json.dumps({'type': 'tool_done', 'tool': tool_use['name']})}\n\n"

        # Add assistant's tool-use message and tool results to conversation
        assistant_content = []
        if full_response:
            assistant_content.append({"type": "text", "text": full_response})
        for tu in tool_uses:
            assistant_content.append({
                "type": "tool_use",
                "id": tu["id"],
                "name": tu["name"],
                "input": tu["input"],
            })

        anthropic_messages.append({"role": "assistant", "content": assistant_content})
        anthropic_messages.append({"role": "user", "content": tool_result_content})

    yield f"data: {json.dumps({'type': 'done'})}\n\n"


async def generate_summary(messages: List[Dict], project_name: str) -> str:
    """Summarise older conversation messages to compress context."""
    history_text = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in messages
    )
    response = await _client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": (
                f"Summarise the following property project discussion for '{project_name}' "
                f"in 400 words. Focus on key decisions, facts, financial figures, and strategic "
                f"directions discussed. Preserve specific numbers and commitments.\n\n{history_text}"
            ),
        }],
    )
    return response.content[0].text
