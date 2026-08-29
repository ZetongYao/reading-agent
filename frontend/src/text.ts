export function sentenceFor(text: string, start: number, end: number) {
  const before = text.slice(0, start)
  const leftMatches = [...before.matchAll(/[.!?]["'”’)]*\s+/g)]
  const left = leftMatches.length
    ? (leftMatches.at(-1)?.index ?? 0) + (leftMatches.at(-1)?.[0].length ?? 0)
    : 0
  const after = text.slice(end)
  const rightMatch = after.match(/[.!?]["'”’)]*(?:\s+|$)/)
  const right = rightMatch?.index !== undefined
    ? end + rightMatch.index + rightMatch[0].trimEnd().length
    : text.length
  return text.slice(left, right).trim()
}
