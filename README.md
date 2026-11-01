# JARVIS Blue Mobile Beta

Static mobile UI at https://mihran94.github.io/JARVIS-Mobile-Beta/ . The Neural Orb, Tamil chat, Gemini/Ollama selector, and HTTPS gateway settings are included. **AI does not work until you deploy and configure your own private gateway.**

## Security
- This public repository does not contain API keys or private Windows/Android source.
- Do not enter your Gemini API key in the website. The website only accepts a **separate gateway access token**, held in page memory and cleared on refresh.
- When connected, chat text is sent to your chosen AI service. No microphone access.
- The gateway example is in `gateway/worker.mjs`. Its shared access token is a basic beta gate, not multi-user authentication. Use a strong random secret and add rate limiting / Cloudflare Access before public rollout.
- **Do not expose the Ollama API directly to the internet.** Ollama requires a separately authenticated, private HTTPS connection to your Windows laptop; the gateway example deliberately does not set that up.

## Optional Cloudflare Worker deployment (Gemini)
1. Create a Cloudflare Workers project, put `gateway/worker.mjs` into the Worker and deploy.
2. Set Worker secret `ACCESS_TOKEN` to a long random gateway token and `GEMINI_API_KEY` to your Gemini API key. Never commit either secret. Set `ALLOWED_ORIGIN` to `https://mihran94.github.io` (default).
3. In the Mobile Beta page, enter the Worker's **HTTPS** URL and the separate `ACCESS_TOKEN`, choose Gemini, and send a test message.
4. Protect usage with rate limits and review Cloudflare/Gemini free-tier quotas; AI calls may incur charges.

## Ollama
Ollama selection is implemented in the client and gateway, but cannot connect until a private HTTPS Windows-to-Worker path is configured. `OLLAMA_URL` must be a private, authenticated HTTPS endpoint and `OLLAMA_TOKEN` is optional for an upstream that supports it. Do not set `OLLAMA_URL` to a publicly exposed, unprotected Ollama instance.

## GitHub Pages
Settings → Pages → Deploy from a branch → `main` / `(root)`. No backend or API keys run on GitHub Pages.
