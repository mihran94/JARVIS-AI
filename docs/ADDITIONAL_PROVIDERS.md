# Additional cloud providers

DeepSeek, Groq and OpenRouter are available alongside OpenAI, MiniMax and Gemini in configuration, chat, connection checks and per-message backup selection.

In API Providers, select the service, enter its own API key locally, review the model ID, then Save provider configuration. Use Test saved provider connection to approve a small billable request. Keys use the existing Windows Credential Manager boundary, never SQLite or source files.

DeepSeek suggests deepseek-flash; Groq suggests openai/gpt-oss-120b. Model IDs remain editable and account availability is not guaranteed. OpenRouter has no default model: enter an exact model ID from your account. OpenRouter is a routing service and sends requests to downstream providers according to its account/routing policies. JARVIS backup consent controls only additional JARVIS-level requests; it does not control routing within that service.

Text streaming only; no provider tools are enabled. Each key is sent only to its fixed service endpoint. Existing cancellation, sanitized errors, no redirects and explicit backup boundaries apply. No live credentials were used during development. Validation: 116 local tests pass, including mocked streaming, usage, auth-error handling and Qt selectors. Real account and Windows checks remain pending.

Official references checked 2026-11-09:
- https://api-docs.deepseek.com/
- https://console.groq.com/docs/openai
- https://console.groq.com/docs/models
- https://openrouter.ai/docs/quickstart
