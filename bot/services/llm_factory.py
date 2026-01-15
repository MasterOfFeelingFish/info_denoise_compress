"""
LLM Factory - Provider factory for creating LLM instances

Provides a centralized factory for creating LLM provider instances
based on configuration.
"""

import logging
from typing import Optional

from .llm_provider import LLMProvider
from .gemini_provider import GeminiProvider
from .openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

# Global singleton instance
_llm_provider: Optional[LLMProvider] = None


class LLMFactory:
    """Factory class for creating LLM provider instances."""

    @staticmethod
    def create_provider(provider_name: str) -> LLMProvider:
        """
        Create an LLM provider based on the provider name.

        Args:
            provider_name: Provider name ('gemini' or 'openai')

        Returns:
            LLMProvider instance

        Raises:
            ValueError: If provider name is unknown
        """
        provider_name = provider_name.lower().strip()

        if provider_name == "gemini":
            from config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_API_URL
            logger.info("Creating Gemini provider")
            return GeminiProvider(
                api_key=GEMINI_API_KEY,
                model=GEMINI_MODEL,
                api_url=GEMINI_API_URL or None
            )

        elif provider_name == "openai":
            from config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_API_URL
            logger.info("Creating OpenAI provider")
            return OpenAIProvider(
                api_key=OPENAI_API_KEY,
                model=OPENAI_MODEL,
                api_url=OPENAI_API_URL or None
            )

        else:
            raise ValueError(
                f"Unknown LLM provider: {provider_name}. "
                f"Supported providers: 'gemini', 'openai'"
            )

    @staticmethod
    def get_provider() -> LLMProvider:
        """
        Get the global LLM provider instance (singleton).

        Returns:
            LLMProvider instance based on LLM_PROVIDER environment variable
        """
        global _llm_provider

        if _llm_provider is None:
            from config import LLM_PROVIDER
            logger.info(f"Initializing LLM provider: {LLM_PROVIDER}")
            _llm_provider = LLMFactory.create_provider(LLM_PROVIDER)

        return _llm_provider

    @staticmethod
    def reset():
        """Reset the global provider instance (for testing)."""
        global _llm_provider
        _llm_provider = None


# Convenience function for backward compatibility
def get_llm() -> LLMProvider:
    """
    Get the global LLM provider instance.

    Returns:
        LLMProvider instance
    """
    return LLMFactory.get_provider()
