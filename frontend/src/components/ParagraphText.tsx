import { memo, useRef, type MutableRefObject } from 'react'
import type { Paragraph } from '../types'

export interface TextSelection {
  paragraphId: number
  start: number
  end: number
  text: string
  x: number
  y: number
}

interface WordSelection {
  paragraphId: number
  start: number
  end: number
  text: string
}

interface Props {
  paragraph: Paragraph
  onWord: (selection: WordSelection) => void
  onPhrase: (selection: TextSelection) => void
}

const wordPattern = /[A-Za-z]+(?:['’-][A-Za-z]+)*/g

function sourcePieces(
  text: string,
  absoluteStart: number,
  paragraphText: string,
  onWord: Props['onWord'],
  onPhrase: Props['onPhrase'],
  paragraphId: number,
  dragStart: MutableRefObject<WordSelection | null>,
  suppressClick: MutableRefObject<boolean>,
) {
  const parts = []
  let cursor = 0
  for (const match of text.matchAll(wordPattern)) {
    const index = match.index
    if (index > cursor) {
      const value = text.slice(cursor, index)
      parts.push(
        <span key={`t-${absoluteStart + cursor}`} data-source="true" data-start={absoluteStart + cursor}>{value}</span>,
      )
    }
    const value = match[0]
    const start = absoluteStart + index
    parts.push(
      <span
        role="button"
        tabIndex={0}
        className="word-token"
        key={`w-${start}`}
        data-source="true"
        data-start={start}
        onClick={(event) => {
          event.stopPropagation()
          if (suppressClick.current) {
            suppressClick.current = false
            return
          }
          if (window.getSelection()?.toString()) return
          onWord({ paragraphId, start, end: start + value.length, text: value })
        }}
        onPointerDown={(event) => {
          if (event.button !== 0) return
          dragStart.current = { paragraphId, start, end: start + value.length, text: value }
        }}
        onPointerUp={(event) => {
          const initial = dragStart.current
          dragStart.current = null
          if (!initial || initial.start === start) return
          const phraseStart = Math.min(initial.start, start)
          const phraseEnd = Math.max(initial.end, start + value.length)
          suppressClick.current = true
          window.getSelection()?.removeAllRanges()
          onPhrase({
            paragraphId,
            start: phraseStart,
            end: phraseEnd,
            text: paragraphText.slice(phraseStart, phraseEnd),
            x: event.clientX,
            y: event.clientY,
          })
        }}
        onKeyDown={(event) => {
          if (event.key !== 'Enter' && event.key !== ' ') return
          event.preventDefault()
          onWord({ paragraphId, start, end: start + value.length, text: value })
        }}
      >{value}</span>,
    )
    cursor = index + value.length
  }
  if (cursor < text.length) {
    parts.push(
      <span key={`t-${absoluteStart + cursor}`} data-source="true" data-start={absoluteStart + cursor}>{text.slice(cursor)}</span>,
    )
  }
  return parts
}

function closestSource(node: Node, root: HTMLElement): HTMLElement | null {
  let element = node.nodeType === Node.ELEMENT_NODE ? node as HTMLElement : node.parentElement
  while (element && element !== root) {
    if (element.dataset.source === 'true') return element
    element = element.parentElement
  }
  return null
}

function localOffset(node: Node, offset: number, source: HTMLElement) {
  if (node.nodeType === Node.TEXT_NODE) return offset
  const range = document.createRange()
  range.selectNodeContents(source)
  try {
    range.setEnd(node, offset)
    return range.toString().length
  } catch {
    return 0
  }
}

export const ParagraphText = memo(function ParagraphText({ paragraph, onWord, onPhrase }: Props) {
  const rootRef = useRef<HTMLParagraphElement>(null)
  const dragStart = useRef<WordSelection | null>(null)
  const suppressClick = useRef(false)
  const annotations = [...paragraph.annotations]
    .filter((item) => item.start_offset >= 0 && item.end_offset <= paragraph.text.length)
    .sort((a, b) => a.start_offset - b.start_offset || a.end_offset - b.end_offset)

  const rendered = []
  let cursor = 0
  for (const annotation of annotations) {
    if (annotation.start_offset < cursor) continue
    rendered.push(...sourcePieces(
      paragraph.text.slice(cursor, annotation.start_offset),
      cursor,
      paragraph.text,
      onWord,
      onPhrase,
      paragraph.id,
      dragStart,
      suppressClick,
    ))
    rendered.push(
      <span
        className="annotated-source"
        data-source="true"
        data-start={annotation.start_offset}
        key={`source-${annotation.id}`}
      >{paragraph.text.slice(annotation.start_offset, annotation.end_offset)}</span>,
    )
    rendered.push(<span className="inline-annotation" aria-label={`中文释义：${annotation.chinese_annotation}`} key={`a-${annotation.id}`}>（{annotation.chinese_annotation}）</span>)
    cursor = annotation.end_offset
  }
  rendered.push(...sourcePieces(
    paragraph.text.slice(cursor),
    cursor,
    paragraph.text,
    onWord,
    onPhrase,
    paragraph.id,
    dragStart,
    suppressClick,
  ))

  const handleSelection = () => {
    const root = rootRef.current
    const selection = window.getSelection()
    if (!root || !selection || selection.isCollapsed || selection.rangeCount === 0) return
    const range = selection.getRangeAt(0)
    if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return
    const startSource = closestSource(range.startContainer, root)
    const endSource = closestSource(range.endContainer, root)
    if (!startSource || !endSource) return
    let start = Number(startSource.dataset.start) + localOffset(range.startContainer, range.startOffset, startSource)
    let end = Number(endSource.dataset.start) + localOffset(range.endContainer, range.endOffset, endSource)
    if (start > end) [start, end] = [end, start]
    while (start < end && /\s/.test(paragraph.text[start])) start += 1
    while (end > start && /\s/.test(paragraph.text[end - 1])) end -= 1
    const text = paragraph.text.slice(start, end)
    if (!text || text.length > 300 || !/[A-Za-z]/.test(text)) return
    const rect = range.getBoundingClientRect()
    onPhrase({ paragraphId: paragraph.id, start, end, text, x: rect.left + rect.width / 2, y: rect.bottom + 8 })
  }

  return (
    <p ref={rootRef} className="reader-paragraph" data-paragraph-id={paragraph.id} onMouseUp={handleSelection}>
      {rendered}
    </p>
  )
})
