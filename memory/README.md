# memory — the notes the owner keeps between sessions

Implemented. `memory/memory_service.py` keeps short notes with a title, some
text and a few tags in the same local SQLite file as the conversation
history, so one encrypted file holds everything and nothing leaves the
machine.

The search is a keyword search with the BM25 weight. There is no embedding
model and no vector store: a model would have to be downloaded and run on
every machine, and the owner would have to trust it with the text of every
note. A keyword search works offline and can be checked.

The **Memory** page of the desktop writes, finds and forgets notes. The
memories that match a question are put in front of the provider as context,
and nothing else is sent. The tests are `tests/test_memory_service.py` and
`tests/test_memory_page.py`.
