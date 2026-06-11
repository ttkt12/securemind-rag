from config import AI_BASE_URL, AI_MODEL, MAX_TOKENS, get_api_key
from openai import OpenAI

client = OpenAI(
    base_url=AI_BASE_URL,
    api_key=get_api_key(),
)

response = client.chat.completions.create(
    model=AI_MODEL,
    messages=[
        {
            "role": "system",
            "content": "You are a helpful assistant. Answer concisely.",
        },
        {
            "role": "user",
            "content": "What is RAG?",
        },
    ],
    temperature=0.2,
    max_tokens=MAX_TOKENS,
    extra_body={"enable_thinking": False},
)

answer = (response.choices[0].message.content or "").strip()
if not answer:
    raise RuntimeError(
        "The model authenticated, but it did not return final content. "
        "Increase MAX_TOKENS in .env."
    )

print(answer)
