from __future__ import annotations

import functools
import logging

from typing import Any

from .usage import normalize_usage

logger = logging.getLogger(__name__)

DIRECT_CHAT_PROMPT = """You are a personal assistant for a single user on Discord.
Answer in the user's language and output only the final response.
Use recent conversation only when relevant."""


class DirectChat:
    def __init__(
        self,
        *,
        model: str,
        project: str,
        secret_name: str,
        aws_access_key_id: str,
        aws_secret_access_key: str,
        aws_region: str,
        max_output_tokens: int,
    ) -> None:
        self.model = model
        self.project = project
        self.secret_name = secret_name
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.aws_region = aws_region
        self.max_output_tokens = max_output_tokens

    @functools.lru_cache(maxsize=1)
    def _bearer(self) -> str:
        import boto3

        secrets = boto3.client(
            "secretsmanager",
            region_name=self.aws_region,
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
        )
        return secrets.get_secret_value(
            SecretId=self.secret_name
        )["SecretString"]

    @functools.lru_cache(maxsize=1)
    def _client(self):
        from openai import AsyncOpenAI

        return AsyncOpenAI(
            base_url=f"https://bedrock-mantle.{self.aws_region}.api.aws/openai/v1",
            api_key=self._bearer(),
            project=self.project,
            max_retries=3,
            timeout=120.0,
        )

    async def call(
        self, question: str, history: list[dict[str, Any]]
    ) -> tuple[str, dict[str, int]]:
        from openai import AuthenticationError

        messages = [
            {
                "type": "message",
                "role": "developer",
                "content": [
                    {"type": "input_text", "text": DIRECT_CHAT_PROMPT}
                ],
            },
            *history,
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": question}],
            },
        ]

        try:
            response = await self._client().responses.create(
                model=self.model,
                input=messages,
                max_output_tokens=self.max_output_tokens,
                store=False,
            )
        except AuthenticationError:
            logger.warning(
                "Direct API authentication failed; refreshing bearer token"
            )
            self._bearer.cache_clear()
            self._client.cache_clear()

            response = await self._client().responses.create(
                model=self.model,
                input=messages,
                max_output_tokens=self.max_output_tokens,
                store=False,
            )

        answer = response.output_text.strip()

        logger.info(
            "Direct API response: request_id=%s status=%s output_text_len=%d",
            getattr(response, "_request_id", None),
            getattr(response, "status", None),
            len(answer),
        )

        if not answer:
            logger.error(
                "Direct API returned no text: "
                "request_id=%s status=%s output=%r incomplete_details=%r",
                getattr(response, "_request_id", None),
                getattr(response, "status", None),
                getattr(response, "output", None),
                getattr(response, "incomplete_details", None),
            )
            raise RuntimeError(
                "Direct API가 텍스트 출력을 반환하지 않았습니다."
            )

        usage = response.usage
        if hasattr(usage, "model_dump"):
            usage = usage.model_dump()

        return answer, normalize_usage(
            usage if isinstance(usage, dict) else {}
        )