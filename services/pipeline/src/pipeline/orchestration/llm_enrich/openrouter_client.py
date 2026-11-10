import os
import requests


def generate_summary(prompt):
    response = requests.post(
        'https://openrouter.ai/api/v1/chat/completions',
        headers={'Authorization': f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
        json={
            'model': os.environ['OPENROUTER_MODEL'],
            'messages': [{'role': 'user', 'content': prompt}],
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content']
