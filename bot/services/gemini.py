"""
Gemini 3 Pro REST API Service

Implements Google Gemini 3 Pro API calls using httpx for async HTTP requests.
Uses REST API directly for maximum control and compatibility.

Supports:
- Custom API URL (for proxies or different regions)
- Model selection via environment variable
- Thinking mode (thinking_level: LOW/HIGH)
- Thought signatures in response
- JSON structured output
- Automatic retry on network errors

Reference: https://ai.google.dev/gemini-api/docs/thinking
"""
import asyncio
import httpx
import json
import logging
from typing import Optional, Tuple

from config import GEMINI_API_KEY, GEMINI_API_URL, GEMINI_MODEL, GEMINI_THINKING_LEVEL

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds


class GeminiService:
    """Gemini 3 Pro REST API wrapper with thinking support."""

    def __init__(self, api_key: Optional[str] = None, api_url: Optional[str] = None):
        self.api_key = api_key or GEMINI_API_KEY
        self.api_url = api_url or GEMINI_API_URL
        self.model = GEMINI_MODEL
        self.thinking_level = GEMINI_THINKING_LEVEL

        if not self.api_key:
            logger.warning("GEMINI_API_KEY not set. API calls will fail.")

        logger.info(f"Gemini API: model={self.model}, thinking={self.thinking_level}")

    async def generate_content(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 1.0,
        max_output_tokens: int = 8192,
        response_mime_type: Optional[str] = None,
        thinking_level: Optional[str] = None,
        include_thoughts: bool = False,
        enable_search: bool = False,
    ) -> str | Tuple[str, str]:
        """
        Generate content using Gemini 3 Pro REST API.

        Args:
            prompt: The user prompt/question
            system_instruction: Optional system instruction for context
            temperature: Sampling temperature (0.0-2.0)
            max_output_tokens: Maximum tokens in response
            response_mime_type: Optional MIME type for structured output
            thinking_level: Override thinking level (LOW/HIGH)
            include_thoughts: If True, returns (response, thoughts) tuple
            enable_search: If True, enables Google Search grounding

        Returns:
            Generated text response, or (response, thoughts) if include_thoughts=True
        """
        headers = {
            "Content-Type": "application/json",
        }

        # Use thinkingConfig for Gemini 3 Pro
        thinking = thinking_level or self.thinking_level

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
                "thinkingConfig": {
                    "thinkingLevel": thinking
                }
            }
        }

        # Add system instruction if provided
        if system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction}]
            }

        # Add response MIME type for JSON output
        if response_mime_type:
            payload["generationConfig"]["responseMimeType"] = response_mime_type

        # Add Google Search grounding tool
        if enable_search:
            payload["tools"] = [{"google_search": {}}]

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.api_url}?key={self.api_key}",
                        json=payload,
                        headers=headers,
                        timeout=120.0  # 2 minutes timeout
                    )
                    response.raise_for_status()
                    result = response.json()

                    # Extract response and thoughts from candidates
                    candidate = result["candidates"][0]["content"]

                    response_text = ""
                    thoughts_text = ""

                    for part in candidate.get("parts", []):
                        if part.get("thought"):
                            # This is thinking/reasoning content
                            thoughts_text += part.get("text", "")
                        else:
                            # This is the actual response
                            response_text += part.get("text", "")

                    if include_thoughts:
                        return response_text, thoughts_text
                    return response_text

            except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError) as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"Gemini API network error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"Gemini API network error after {MAX_RETRIES} attempts: {e}")
                    raise
            except httpx.HTTPStatusError as e:
                logger.error(f"Gemini API HTTP error: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.TimeoutException:
                last_error = httpx.TimeoutException("Request timeout")
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"Gemini API timeout (attempt {attempt + 1}/{MAX_RETRIES})")
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"Gemini API timeout after {MAX_RETRIES} attempts")
                    raise
            except (KeyError, IndexError) as e:
                logger.error(f"Gemini API response parsing error: {e}")
                raise

        # Should not reach here, but just in case
        if last_error:
            raise last_error

    async def generate_json(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 1.0,
    ) -> dict:
        """
        Generate JSON-structured content.

        Args:
            prompt: The user prompt/question
            system_instruction: Optional system instruction
            temperature: Sampling temperature

        Returns:
            Parsed JSON dict
        """
        response_text = await self.generate_content(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=temperature,
            response_mime_type="application/json"
        )

        # Parse and return JSON
        try:
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini JSON response: {e}")
            # Try to extract JSON from markdown code blocks
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
                return json.loads(json_str)
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
                return json.loads(json_str)
            raise

    async def generate_with_thoughts(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 1.0,
    ) -> Tuple[str, str]:
        """
        Generate content and return both response and thinking process.

        Args:
            prompt: The user prompt/question
            system_instruction: Optional system instruction
            temperature: Sampling temperature

        Returns:
            Tuple of (response_text, thoughts_text)
        """
        return await self.generate_content(
            prompt=prompt,
            system_instruction=system_instruction,
            temperature=temperature,
            include_thoughts=True,
        )


# Singleton instance
gemini_service = GeminiService()


async def call_gemini(
    prompt: str,
    system_instruction: Optional[str] = None,
    temperature: float = 1.0,
) -> str:
    """
    Convenience function for generating content with Gemini.

    Args:
        prompt: User prompt
        system_instruction: Optional system context
        temperature: Sampling temperature (default 1.0)

    Returns:
        Generated text
    """
    return await gemini_service.generate_content(
        prompt=prompt,
        system_instruction=system_instruction,
        temperature=temperature,
    )


async def call_gemini_json(
    prompt: str,
    system_instruction: Optional[str] = None,
) -> dict:
    """
    Convenience function for generating JSON with Gemini.

    Args:
        prompt: User prompt
        system_instruction: Optional system context

    Returns:
        Parsed JSON dict
    """
    return await gemini_service.generate_json(
        prompt=prompt,
        system_instruction=system_instruction,
    )


async def call_gemini_with_thoughts(
    prompt: str,
    system_instruction: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Generate content and return thinking process.

    Args:
        prompt: User prompt
        system_instruction: Optional system context

    Returns:
        Tuple of (response, thoughts)
    """
    return await gemini_service.generate_with_thoughts(
        prompt=prompt,
        system_instruction=system_instruction,
    )


async def call_gemini_with_search(
    prompt: str,
    system_instruction: Optional[str] = None,
    temperature: float = 1.0,
) -> str:
    """
    Generate content with Google Search grounding enabled.

    Args:
        prompt: User prompt
        system_instruction: Optional system context
        temperature: Sampling temperature (default 1.0)

    Returns:
        Generated text with grounded information
    """
    return await gemini_service.generate_content(
        prompt=prompt,
        system_instruction=system_instruction,
        temperature=temperature,
        enable_search=True,
    )
