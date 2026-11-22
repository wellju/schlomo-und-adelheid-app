// Next version label for a new configuration state: the trailing number counts up ("syn-1" -> "syn-2", "3" -> "4").
export function naechsteVersion(v: string, vergeben: string[] = []): string {
  const m = /^(.*?)(\d+)$/.exec(v);
  let n = m ? Number(m[2]) + 1 : 2;
  const basis = m ? m[1] : `${v}-`;
  while (vergeben.includes(`${basis}${n}`) || `${basis}${n}` === v) n += 1;
  return `${basis}${n}`;
}
