// Hash router: #/faelle, #/fall/<session_id>/<bereich>, #/einstellungen ... No router package needed.
function parse(): string[] {
  const parts = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent);
  return parts.length ? parts : ['faelle'];
}

export const route = $state({ teile: parse() });
window.addEventListener('hashchange', () => { route.teile = parse(); });

export const href = (...teile: string[]) => '#/' + teile.map(encodeURIComponent).join('/');
export function gehe(...teile: string[]) { location.hash = href(...teile); }
