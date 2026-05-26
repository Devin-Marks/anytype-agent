"""Input and output guardrail nodes."""
import logging
from typing import Optional

from ..state import AgentState

# Note: NeMo Guardrails is optional. If not installed, guardrails will be bypassed.
try:
    from nemoguardrails import LLMRails, RailsConfig
    NEMO_AVAILABLE = True
except ImportError:
    NEMO_AVAILABLE = False
    LLMRails = None
    RailsConfig = None

logger = logging.getLogger(__name__)

# Singleton rails instance
_rails: Optional["LLMRails"] = None


def get_rails() -> Optional["LLMRails"]:
    """Get or create NeMo Guardrails instance."""
    global _rails
    
    if not NEMO_AVAILABLE:
        logger.warning("NeMo Guardrails not available, guardrails will be bypassed")
        return None
    
    if _rails is None:
        from ..config import get_settings
        settings = get_settings()
        config = RailsConfig.from_path(settings.guardrails_config_path)
        _rails = LLMRails(config)
    
    return _rails


def _is_refusal(result) -> bool:
    """Check if NeMo result indicates a refusal."""
    content = result.get("content", "").lower()
    return "i cannot" in content or "i'm not able" in content or "refuse" in content


async def input_guardrail(state: AgentState) -> dict:
    """Input guardrail node - checks user input before processing.

    Per langgraph.md: "Fail-open with logging on input rails is a reasonable default."
    """
    rails = get_rails()
    
    # If no rails configured, proceed
    if rails is None:
        return {"blocked": False}
    
    user_input = state["user_request"]

    try:
        result = await rails.generate_async(messages=[
            {"role": "user", "content": user_input}
        ])

        if _is_refusal(result):
            return {
                "blocked": True,
                "block_reason": "Input blocked by guardrail: content policy violation",
            }
    except Exception as e:
        # Fail-open on input rails with logging
        logger.warning(f"Input guardrail check failed: {e}")

    return {"blocked": False}


async def output_guardrail(state: AgentState) -> dict:
    """Output guardrail node - checks response before returning.

    Per langgraph.md: "Fail-closed on output rails is a reasonable default."
    """
    rails = get_rails()
    user_input = state["user_request"]
    output = state.get("output", "")

    # If no rails configured or no output, proceed
    if rails is None or not output:
        return {"blocked": False}

    try:
        result = await rails.generate_async(messages=[
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": output},
        ])

        if _is_refusal(result):
            return {
                "blocked": True,
                "output": "I cannot help with that.",
                "block_reason": "Output blocked by guardrail: content policy violation",
            }
    except Exception as e:
        # Fail-closed on output rails
        logger.error(f"Output guardrail check failed: {e}")
        return {
            "blocked": True,
            "output": "I cannot help with that.",
            "block_reason": "Output guardrail check failed",
        }

    return {"blocked": False}