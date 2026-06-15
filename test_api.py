import sys, os, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from pathlib import Path

for line in Path(".env").read_text(encoding="utf-8-sig").splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

import httpx, anthropic
client = anthropic.Anthropic(
    api_key=os.environ["ANTHROPIC_API_KEY"],
    http_client=httpx.Client(verify=False),
)

msg = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=200,
    messages=[
        {"role": "user", "content": 'Retorne apenas JSON valido: {"status": "OK", "valor": 42}'},
        {"role": "assistant", "content": "{"},
    ],
)
resposta = "{" + msg.content[0].text
print("Resposta:", repr(resposta[:150]))
print("JSON ok:", json.loads(resposta))
