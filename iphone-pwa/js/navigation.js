// Switching sections never changes the URL or reloads in-memory pairing.
export function createNavigation(documentRef, onChange = () => {}) {
  const links = [...documentRef.querySelectorAll('.remote-nav a')];
  const panels = links.map((link) => documentRef.getElementById(link.getAttribute('href').slice(1)));
  function show(id) {
    if (!panels.some((panel) => panel?.id === id)) return false;
    for (let i = 0; i < panels.length; i += 1) {
      panels[i].hidden = panels[i].id !== id;
      if (panels[i].id === id) links[i].setAttribute('aria-current', 'page');
      else links[i].removeAttribute('aria-current');
    }
    onChange(id);
    return true;
  }
  for (const link of links) link.addEventListener('click', (event) => {
    event.preventDefault();
    show(link.getAttribute('href').slice(1));
  });
  show('pairing');
  return { show };
}
