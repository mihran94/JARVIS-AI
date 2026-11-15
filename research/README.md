# research — reading a page the owner names

Implemented. `research/research.py` reads one page that the owner gives and
puts its text in front of the provider, which answers from that text only.

The rules that keep it safe:

- only `https`, and a page that resolves to a private, loopback or
  link-local address is refused, so a link cannot reach the machines inside
  the owner's own network;
- the page size and the time are limited;
- the provider is never asked to fetch anything itself, so it cannot follow
  a link that is in the page.

The **Research a page** button on the chat page opens the window. The reading
happens on a worker thread, so the interface never freezes. The tests are
`tests/test_research.py` and `tests/test_research_dialog.py`.
