import os
import requests


class OpenRouterBudgetExhausted(Exception):
    """OpenRouter budget or credit restriction."""


class OpenRouterRateLimited(Exception):
    """OpenRouter request throttling."""


def generate_summary(prompt):
    response = requests.post(
        'https://openrouter.ai/api/v1/chat/completions',
        headers={
            'Authorization': (
                f"Bearer {os.environ['OPENROUTER_API_KEY']}"
            )
        },
        json={
            'model': os.environ['OPENROUTER_MODEL'],
            'messages': [
                {
                    'role': 'user',
                    'content': prompt
                }
            ]
        },
        timeout=30
    )

    if response.status_code in (402, 429):
        try:
            error = response.json().get('error', {})
        except ValueError:
            error = {}

        message = error.get('message', response.text)
        metadata = error.get('metadata') or {}

        if response.status_code == 402:
            raise OpenRouterBudgetExhausted(
                f'{message}; metadata={metadata}'
            )

        raise OpenRouterRateLimited(
            f'{message}; metadata={metadata}'
        )

    response.raise_for_status()

    data = response.json()

    return (
        data['choices'][0]['message']['content'],
        data['model']
    )