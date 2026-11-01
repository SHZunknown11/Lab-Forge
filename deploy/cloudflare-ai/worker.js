// LabForge AI proxy: an OpenAI-style /v1/chat/completions endpoint in front of
// Workers AI, so the backend can use Cloudflare's free daily allowance with one key.
//
// Bindings: AI (Workers AI), KEY_SHA256 (secret: sha256 hex of the key the backend
// sends as "Authorization: Bearer <key>"), DEFAULT_MODEL (plain text).
// Deploy: see README.md in this folder.

const MODELS = new Set([
  "@cf/openai/gpt-oss-120b",
  "@cf/openai/gpt-oss-20b",
  "@cf/google/gemma-4-26b-a4b-it",
  "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
  "@cf/meta/llama-4-scout-17b-16e-instruct",
  "@cf/mistralai/mistral-small-3.1-24b-instruct",
  "@cf/qwen/qwen3-30b-a3b-fp8",
  "@cf/deepseek-ai/deepseek-v4.1-flash-1017",
]);

const enc = new TextEncoder();

async function sha256hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", enc.encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function fail(message, status) {
  return json({ error: { message } }, status);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/") return json({ ok: true, service: "labforge-ai" });
    if (request.method !== "POST" || url.pathname !== "/v1/chat/completions") {
      return fail("not found", 404);
    }

    const token = (request.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
    if (!token || (await sha256hex(token)) !== env.KEY_SHA256) return fail("unauthorized", 401);

    let body;
    try {
      body = await request.json();
    } catch {
      return fail("bad json", 400);
    }
    const model = body.model || env.DEFAULT_MODEL;
    if (!MODELS.has(model)) return fail(`model not allowed: ${model}`, 400);
    if (!Array.isArray(body.messages)) return fail("messages required", 400);

    const input = {
      messages: body.messages,
      max_tokens: Math.min(Number(body.max_tokens) || 8000, 16000),
      temperature: typeof body.temperature === "number" ? body.temperature : 0.2,
    };
    if (body.response_format) input.response_format = body.response_format;
    if (body.reasoning_effort) input.reasoning_effort = body.reasoning_effort;

    let out;
    try {
      out = await env.AI.run(model, input);
    } catch (err) {
      const msg = String((err && err.message) || err).slice(0, 400);
      // 429 lets the backend move on to the next provider (daily free neurons used up, busy).
      if (/429|rate.?limit|capacity|neuron|allocation|too many/i.test(msg)) return fail(msg, 429);
      // The backend retries without response_format when a 400 mentions it.
      if (/json mode|schema/i.test(msg)) return fail(`response_format: ${msg}`, 400);
      return fail(msg, 502);
    }

    if (out && Array.isArray(out.choices)) return json(out);
    // Older models answer { response, usage }; reshape into a chat completion.
    let content = out && out.response;
    if (content && typeof content !== "string") content = JSON.stringify(content);
    return json({
      id: `cf-${Date.now()}`,
      object: "chat.completion",
      model,
      choices: [{ index: 0, message: { role: "assistant", content: content || "" }, finish_reason: "stop" }],
      usage: (out && out.usage) || {},
    });
  },
};
