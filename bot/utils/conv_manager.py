"""
Conversation Manager

Prevents multiple ConversationHandlers from competing for text input.
When a user navigates from one text-awaiting conversation to another,
the first handler would otherwise steal the text input.

Usage:
- Call `activate_conv(context, "conv_name")` in each entry_point that leads to text input
- Call `is_active_conv(context, "conv_name")` in each text MessageHandler
  to check if this conversation is the active one
"""
import logging

logger = logging.getLogger(__name__)

# Key used in context.user_data
_ACTIVE_CONV_KEY = "_active_text_conv"


def activate_conv(context, conv_name: str) -> None:
    """Mark a conversation as the active text-input conversation.
    
    Call this in every entry_point handler that leads to text input.
    """
    prev = context.user_data.get(_ACTIVE_CONV_KEY)
    if prev and prev != conv_name:
        logger.debug(f"Conversation switch: {prev} → {conv_name}")
    context.user_data[_ACTIVE_CONV_KEY] = conv_name


def is_active_conv(context, conv_name: str) -> bool:
    """Check if this conversation is the currently active one.
    
    Returns True if:
    - This conv is the active one, OR
    - No active conv is set (first use / cleared)
    """
    active = context.user_data.get(_ACTIVE_CONV_KEY)
    if active is None:
        return True  # No tracking yet, allow
    return active == conv_name


def clear_active_conv(context) -> None:
    """Clear the active conversation tracker."""
    context.user_data.pop(_ACTIVE_CONV_KEY, None)
