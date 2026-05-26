"""LangGraph builder for the Anytype agent."""
import logging
from typing import Literal

from langgraph.graph import END, StateGraph, START

from .state import AgentState
from .nodes import (
    input_guardrail,
    output_guardrail,
    parse_intent,
    execute_tool,
    format_response,
)

logger = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    """Build and compile the Anytype agent graph."""

    builder = StateGraph(AgentState)

    # Add nodes
    builder.add_node("input_guardrail", input_guardrail)
    builder.add_node("parse_intent", parse_intent)
    builder.add_node("execute_tool", execute_tool)
    builder.add_node("output_guardrail", output_guardrail)
    builder.add_node("format_response", format_response)

    # Set entry point
    builder.add_edge(START, "input_guardrail")

    # Conditional routing from input guardrail
    builder.add_conditional_edges(
        "input_guardrail",
        _should_proceed,
        {
            "blocked": END,  # Stop if blocked
            "proceed": "parse_intent",
        },
    )

    # Normal flow
    builder.add_edge("parse_intent", "execute_tool")
    builder.add_edge("execute_tool", "output_guardrail")

    # Conditional routing from output guardrail
    builder.add_conditional_edges(
        "output_guardrail",
        _check_output_guardrail,
        {
            "blocked": END,
            "proceed": "format_response",
        },
    )

    builder.add_edge("format_response", END)

    return builder.compile()


def _should_proceed(state: AgentState) -> Literal["blocked", "proceed"]:
    """Check if request should proceed after input guardrail."""
    if state.get("blocked", False):
        logger.info("Request blocked by input guardrail")
        return "blocked"
    return "proceed"


def _check_output_guardrail(state: AgentState) -> Literal["blocked", "proceed"]:
    """Check if response should proceed after output guardrail."""
    if state.get("blocked", False):
        logger.info("Output blocked by output guardrail")
        return "blocked"
    return "proceed"


# Singleton compiled graph
_agent_graph = None


def get_graph() -> StateGraph:
    """Get the compiled agent graph (singleton)."""
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_graph()
    return _agent_graph