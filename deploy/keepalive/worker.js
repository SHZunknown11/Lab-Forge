// Keeps the free Render instance awake during Indian daytime (cron in UTC).
// Render sleeps a free service after 15 idle minutes; a ping every 10 minutes
// avoids the ~1 minute cold start for students. The schedule stops at night so
// the workspace's 750 free hours a month also cover other free services.
export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(
      fetch(env.TARGET, { headers: { "user-agent": "labforge-keepalive" } })
        .then((r) => console.log("ping", r.status))
        .catch((e) => console.log("ping failed", String(e)))
    );
  },
  async fetch() {
    return new Response("labforge keep-alive", { status: 200 });
  },
};
