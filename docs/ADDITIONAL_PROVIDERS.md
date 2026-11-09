# Additional cloud providers

DeepSeek, Groq and OpenRouter are available alongside OpenAI, MiniMax and Gemini in configuration, chat, connection checks and per-message backup selection.

In API Providers, select the service, enter its own API key locally, then Save API key. Use Test saved provider connection to approve a small billable request. Keys use the existing Windows Credential Manager boundary, never SQLite or source files.

DeepSeek suggests deepseek-flash; Groq suggests openai/gpt-oss-120b. OpenRouter suggests openai/gpt-4.1-mini. Model IDs are preselected; Advanced settings allows optional overrides or resetting to the recommended model. Existing custom choices are preserved. Account availability is not guaranteed. Saving selects this provider for chat without making a network request. OpenRouter is a routing service and sends requests to downstream providers according to its account/routing policies. JARVIS backup consent controls only additional JARVIS-level requests; it does not control routing within that service.

Text streaming only; no provider tools are enabled. Each key is sent only to its fixed service endpoint. Existing cancellation, sanitized errors, no redirects and explicit backup boundaries apply. No live credentials were used during development. Validation: 123 local tests pass, including mocked streaming, usage, auth-error handling and Qt selectors. Real account and Windows checks remain pending.

Official references checked 2026-11-09:
- https://api-docs.deepseek.com/
- https://console.groq.com/docs/openai
- https://console.groq.com/docs/models
- https://openrouter.ai/docs/quickstart

OpenRouter default reference: https://openrouter.ai/openai/gpt-4.1-mini

தமிழ்: Provider தேர்வு → API key உள்ளிடவும் → Save API key. Model எழுதத் தேவையில்லை. மாற்ற வேண்டுமானால் Advanced settings பயன்படுத்தவும். Connection test தனியாக அனுமதி கேட்கும்.
