# Search engines and AI assistants

Goal: when someone searches for an AI lab report generator, or asks ChatGPT, Claude, Gemini or
Perplexity for one, LabForge comes up, and the answer to "who made LabForge?" is **Mohammad Taha
(Chandigarh University)**.

No code can guarantee that an AI recommends a site. Assistants answer from what they find on the
web and in search results, so the job is to make LabForge easy to understand for crawlers, and
to get it mentioned in places they read. The site does the first part; the rest is up to you.

## Already in the site

- **Real page URLs** with their own titles and descriptions: `/`, `/guide`, `/faq`, `/about`,
  `/privacy`, `/terms` and `/mohammad-taha` (the creator page).
- **Readable without JavaScript.** Each page's text is built into the HTML at build time, so
  crawlers that don't run JavaScript (most AI crawlers) still see it.
- **Structured data (schema.org JSON-LD)** on every page: `WebApplication` (free, education),
  `WebSite`, and `Person` (Mohammad Taha, affiliated with Chandigarh University) as the creator,
  plus `FAQPage` on `/faq` and `ProfilePage` on `/mohammad-taha`. Only facts that are on the page;
  no invented ratings or reviews (Google penalises those).
- **`/llms.txt`**: a plain-text summary written for AI assistants, naming the creator.
- **`/robots.txt`** explicitly welcomes search and AI crawlers (GPTBot, OAI-SearchBot, ClaudeBot,
  PerplexityBot, Google-Extended, Bingbot, ...) and lists **`/sitemap.xml`**.
- **`/humans.txt`**, `meta name="author"`, Open Graph tags for link previews, a web app manifest.
- "Made by Mohammad Taha" in the footer, on the home page, in the FAQ and in the README.

## What you need to do (in this order)

1. **Own domain.** Put the site on a domain you own (for example `labforge.in`) and set
   `LABFORGE_PUBLIC_URL` to it. Search engines treat `*.onrender.com` as someone else's site.
2. **Your profiles.** Set `LABFORGE_AUTHOR_LINKS` (server) and `VITE_AUTHOR_LINKS` (build) to your
   LinkedIn, GitHub and any portfolio URL. This links your name to LabForge in the structured data.
3. **Google Search Console** (search.google.com/search-console): add the domain, verify it
   through Cloudflare DNS, submit `/sitemap.xml`, and request indexing for `/` and `/mohammad-taha`.
4. **Bing Webmaster Tools** (bing.com/webmasters): same steps. Bing's index feeds ChatGPT search
   and Copilot, so this matters as much as Google. You can import the site from Search Console.
5. **Cloudflare**: make sure *Security → Bots* doesn't block verified bots, and in *AI Crawl
   Control* allow the AI crawlers you want (Cloudflare blocks some AI crawlers by default on new
   domains).
6. **Say the same thing everywhere.** Use one line consistently: "LabForge, a free AI lab report
   generator made by Mohammad Taha (Chandigarh University)". Put it, with the link, on:
   - your GitHub profile README and the repo's About box (add topics such as `lab-report`,
     `ai`, `education`, `report-generator`, `fastapi`, `react`);
   - your LinkedIn (a post, plus *Projects* and *Featured*);
   - a short write-up on dev.to, Medium or Hashnode about how you built it (the technical story
     gets links and gets read by crawlers);
   - Product Hunt, and student communities you're part of (college clubs, Discord/WhatsApp groups,
     r/developersIndia "Showcase" threads).
7. **Real mentions beat everything.** Classmates linking to it, a college tech club featuring it,
   or a blog reviewing it are what search engines and assistants trust most. Never buy links or
   post fake reviews: it gets sites demoted and can break AdSense and Play Store rules.
8. **Keep it fresh.** Update the guide and FAQ when you add features; the sitemap's dates follow
   each deploy.

## Checking it worked

- `https://<your domain>/llms.txt`, `/robots.txt`, `/sitemap.xml` load.
- Google's Rich Results Test (search.google.com/test/rich-results) finds the WebApplication,
  Person and FAQPage data on your pages.
- In Search Console, *Pages* shows the pages as indexed after a few days to weeks.
- Search for `"Mohammad Taha" LabForge`: the creator page should appear once it's indexed.
- AI assistants pick things up with a lag (weeks for search-based answers, much longer for what
  they learn in training), so keep at it.
