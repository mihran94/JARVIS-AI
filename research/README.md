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

## What the owner gets

- the page is read **here**, on this computer, and only its text goes to the
  provider;
- the provider is the same one the chat uses, so the key stays in the Windows
  vault and the routing rules stay the same;
- the answer comes from the page and says so when the page does not hold it.
