# JARVIS Blue — November Early Access V73.1

Runnable Python/Tkinter prototype. **Not V80 final**.

## Windows Python 3.12
From this folder run `py -3.12 app.py`.
For Ollama chat, install Ollama, start its local service, and run `ollama pull llama3.2`.
The dashboard opens without Ollama. The **Check Ollama** button probes the loopback service on demand.

## Tests
`py -3.12 -m unittest discover -s tests -v`

The corresponding ZIP passed **15/15 mocked unit tests** in a Linux Python environment. This GitHub branch has **not** been tested on Windows. The desktop GUI and real Ollama service have not been integration-tested. Cloud provider status is configuration-only. Wake word, automation, file editing, sandboxing, signed updates, and installer are not implemented. No API keys are stored in the repo.
