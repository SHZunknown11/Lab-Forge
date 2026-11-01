# Cloudflare Workers AI proxy

A 90-line Worker that exposes Workers AI as an OpenAI-style
`/v1/chat/completions` endpoint, so LabForge can use the free daily allowance
on any Cloudflare account (10,000 neurons a day, roughly 30 sheets with
`@cf/openai/gpt-oss-120b`) through the same code path as Groq or Cerebras.

The backend sends `Authorization: Bearer <key>`; the Worker only stores the
SHA-256 of that key, so the key itself never sits in Cloudflare.

## Deploy

```sh
# 1. make a key and its hash
python -c "import secrets,hashlib;k='lfcf_'+secrets.token_urlsafe(32);print(k);print(hashlib.sha256(k.encode()).hexdigest())"

# 2. deploy (needs `npx wrangler login` once)
cd deploy/cloudflare-ai
npx wrangler deploy
npx wrangler secret put KEY_SHA256      # paste the hash (second line)
```

Then in `.env` (or the host's secrets):

```
CLOUDFLARE_AI_KEY=<the key, first line>
CLOUDFLARE_BASE_URL=https://labforge-ai.<your-subdomain>.workers.dev/v1
```

Check it: `curl https://labforge-ai.<your-subdomain>.workers.dev/` answers
`{"ok":true}`. Requests without the key get 401. When the day's free neurons
run out the Worker answers 429 and LabForge moves on to the next provider.
