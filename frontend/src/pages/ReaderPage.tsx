import { ArrowLeft, BookOpen, LoaderCircle, Menu, Search, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { ParagraphText } from '../components/ParagraphText'
import { WordModal } from '../components/WordModal'
import { sentenceFor } from '../text'
import type { Annotation, AppSettings, Book, Section, TranslationPreview } from '../types'

interface PendingSelection {
  paragraphId: number
  start: number
  end: number
  text: string
  sentence: string
  translation: TranslationPreview | null
}

interface SearchResult {
  paragraph_id: number
  section_id: number
  text: string
  section_title: string
}

export function ReaderPage() {
  const { bookId: rawBookId } = useParams()
  const bookId = Number(rawBookId)
  const [searchParams] = useSearchParams()
  const [book, setBook] = useState<Book | null>(null)
  const [sections, setSections] = useState<Section[]>([])
  const [activeSectionId, setActiveSectionId] = useState<number | null>(null)
  const [settings, setSettings] = useState<AppSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [pending, setPending] = useState<PendingSelection | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [modalError, setModalError] = useState('')
  const [notice, setNotice] = useState('')
  const [search, setSearch] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const readingRef = useRef<HTMLDivElement>(null)
  const progressTimer = useRef<number | null>(null)
  const previewRequest = useRef(0)
  const restoredPosition = useRef(false)
  const initialLocation = useRef({
    sectionId: Number(searchParams.get('section')) || null,
    paragraphId: Number(searchParams.get('paragraph')) || null,
  })

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([api.book(bookId), api.bookContent(bookId), api.settings()])
      .then(([loadedBook, content, loadedSettings]) => {
        if (cancelled) return
        setBook(loadedBook)
        setSections(content.sections)
        setSettings(loadedSettings)
        setActiveSectionId(
          initialLocation.current.sectionId
          ?? loadedBook.progress?.section_id
          ?? content.sections[0]?.id
          ?? null,
        )
        document.documentElement.dataset.theme = loadedSettings.theme
        setError('')
      })
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof Error ? caught.message : '书籍加载失败')
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [bookId])

  useEffect(() => {
    if (loading || restoredPosition.current || sections.length === 0) return
    const root = readingRef.current
    if (!root) return
    const paragraphId = initialLocation.current.paragraphId ?? book?.progress?.paragraph_id
    const sectionId = initialLocation.current.sectionId ?? book?.progress?.section_id
    window.requestAnimationFrame(() => {
      const paragraph = paragraphId ? root.querySelector(`[data-reader-paragraph-id="${paragraphId}"]`) : null
      const section = sectionId ? root.querySelector(`#section-${sectionId}`) : null
      if (paragraph) paragraph.scrollIntoView({ block: 'center' })
      else if (section) section.scrollIntoView({ block: 'start' })
      else if ((book?.progress?.scroll_ratio ?? 0) > 0) {
        root.scrollTop = (root.scrollHeight - root.clientHeight) * (book?.progress?.scroll_ratio ?? 0)
      }
      restoredPosition.current = true
    })
  }, [book, loading, sections])

  useEffect(() => {
    const root = readingRef.current
    if (!root || sections.length === 0) return
    const visible = new Map<Element, IntersectionObserverEntry>()
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) visible.set(entry.target, entry)
        else visible.delete(entry.target)
      }
      if (!restoredPosition.current || visible.size === 0) return
      const current = [...visible.values()].sort((a, b) => {
        const rootTop = root.getBoundingClientRect().top
        return Math.abs(a.boundingClientRect.top - rootTop - 90) - Math.abs(b.boundingClientRect.top - rootTop - 90)
      })[0]
      const element = current.target as HTMLElement
      const sectionId = Number(element.dataset.sectionId)
      const paragraphId = Number(element.dataset.readerParagraphId)
      setActiveSectionId(sectionId)
      if (progressTimer.current) window.clearTimeout(progressTimer.current)
      progressTimer.current = window.setTimeout(() => {
        const denominator = root.scrollHeight - root.clientHeight
        const ratio = denominator > 0 ? root.scrollTop / denominator : 0
        void api.saveProgress(bookId, {
          section_id: sectionId,
          paragraph_id: paragraphId,
          scroll_ratio: Math.max(0, Math.min(1, ratio)),
        })
      }, 500)
    }, { root, rootMargin: '-70px 0px -55% 0px', threshold: 0.01 })
    root.querySelectorAll('[data-reader-paragraph-id]').forEach((element) => observer.observe(element))
    return () => {
      observer.disconnect()
      if (progressTimer.current) window.clearTimeout(progressTimer.current)
    }
  }, [bookId, sections])

  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(''), 2400)
    return () => window.clearTimeout(timer)
  }, [notice])

  const paragraphById = useMemo(() => new Map(
    sections.flatMap((section) => section.paragraphs.map((paragraph) => [paragraph.id, paragraph] as const)),
  ), [sections])
  const activeSection = sections.find((section) => section.id === activeSectionId) ?? sections[0]

  const closeModal = () => {
    if (saving) return
    previewRequest.current += 1
    setPending(null)
    setPreviewing(false)
    setModalError('')
    window.getSelection()?.removeAllRanges()
  }

  const requestPreview = useCallback(async (selection: PendingSelection) => {
    const requestId = ++previewRequest.current
    setPreviewing(true)
    setModalError('')
    try {
      const translation = await api.previewTranslation(selection.text, selection.sentence)
      if (previewRequest.current !== requestId) return
      setPending((current) => current ? { ...current, translation } : current)
    } catch (caught) {
      if (previewRequest.current === requestId) {
        setModalError(caught instanceof Error ? caught.message : '生成释义失败')
      }
    } finally {
      if (previewRequest.current === requestId) setPreviewing(false)
    }
  }, [])

  const openSelection = useCallback((selection: { paragraphId: number; start: number; end: number; text: string }) => {
    const paragraph = paragraphById.get(selection.paragraphId)
    if (!paragraph) return
    const next: PendingSelection = {
      ...selection,
      sentence: sentenceFor(paragraph.text, selection.start, selection.end),
      translation: null,
    }
    setPending(next)
    void requestPreview(next)
  }, [paragraphById, requestPreview])

  const mergeAnnotation = (annotation: Annotation) => {
    setSections((current) => current.map((section) => ({
      ...section,
      paragraphs: section.paragraphs.map((paragraph) => paragraph.id === annotation.paragraph_id
        ? {
            ...paragraph,
            annotations: [
              ...paragraph.annotations.filter((item) => item.id !== annotation.id),
              annotation,
            ],
          }
        : paragraph),
    })))
  }

  const saveSelection = async () => {
    if (!pending?.translation) return
    setSaving(true)
    setModalError('')
    try {
      const annotation = await api.annotate({
        book_id: bookId,
        paragraph_id: pending.paragraphId,
        start_offset: pending.start,
        end_offset: pending.end,
        selected_text: pending.text,
        chinese_annotation: pending.translation.contextual_translation,
        all_chinese_meanings: pending.translation.meanings,
      })
      mergeAnnotation(annotation)
      setPending(null)
      window.getSelection()?.removeAllRanges()
      setNotice(annotation.existing ? '这里已有释义，已直接显示' : `已保存：${pending.text}（${annotation.chinese_annotation}）`)
    } catch (caught) {
      setModalError(caught instanceof Error ? caught.message : '保存释义失败')
    } finally {
      setSaving(false)
    }
  }

  const scrollToLocation = (sectionId: number, paragraphId?: number | null) => {
    const root = readingRef.current
    const target = paragraphId
      ? root?.querySelector(`[data-reader-paragraph-id="${paragraphId}"]`)
      : root?.querySelector(`#section-${sectionId}`)
    target?.scrollIntoView({ behavior: 'smooth', block: paragraphId ? 'center' : 'start' })
    setActiveSectionId(sectionId)
  }

  const runSearch = async () => {
    if (!search.trim()) { setResults([]); return }
    try {
      setResults(await api.searchBook(bookId, search.trim()))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '搜索失败')
    }
  }

  const readerStyle = {
    '--reader-font-size': `${settings?.font_size ?? 20}px`,
    '--reader-line-height': settings?.line_height ?? 1.9,
  } as CSSProperties

  return (
    <div className="reader-page">
      <header className="reader-topbar">
        <Link to="/shelf" className="icon-button" aria-label="返回书架"><ArrowLeft size={19} /></Link>
        <button className="icon-button" onClick={() => setSidebarOpen((value) => !value)} aria-label="切换目录" aria-expanded={sidebarOpen}><Menu size={19} /></button>
        <div className="reader-book-title"><strong>{book?.title || '正在打开…'}</strong><span>{activeSection?.title || '整本连续阅读'}</span></div>
        <div className="reader-hint">向下滚动整本书 · 单击单词 · 拖选词组即译</div>
      </header>
      <div className="reader-layout">
        <aside className={`reader-sidebar${sidebarOpen ? ' open' : ''}`} aria-hidden={!sidebarOpen} inert={sidebarOpen ? undefined : true}>
          <div className="toc-title"><BookOpen size={17} /><strong>目录</strong><span>{sections.length}</span></div>
          <div className="book-search">
            <Search size={15} />
            <input value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && void runSearch()} placeholder="搜索全书" aria-label="搜索全书" />
            {search && <button aria-label="清除搜索" onClick={() => { setSearch(''); setResults([]) }}><X size={14} /></button>}
          </div>
          {results.length > 0 ? <div className="search-results">
            <span className="result-count">找到 {results.length} 处</span>
            {results.map((result) => <button key={result.paragraph_id} onClick={() => scrollToLocation(result.section_id, result.paragraph_id)}>
              <strong>{result.section_title}</strong><span>{result.text.slice(0, 90)}{result.text.length > 90 ? '…' : ''}</span>
            </button>)}
          </div> : <nav className="toc-list">
            {sections.map((section) => <button className={section.id === activeSectionId ? 'active' : ''} key={section.id} onClick={() => scrollToLocation(section.id)}>
              <span>{section.order_index + 1}</span><strong>{section.title}</strong>
            </button>)}
          </nav>}
        </aside>

        <main className="reading-column" ref={readingRef} data-testid="continuous-reader">
          {loading ? <div className="reader-loading"><LoaderCircle className="spin" /><span>正在排版整本书…</span></div> : error ? <div className="empty-state"><h2>暂时无法打开</h2><p>{error}</p></div> : sections.length > 0 ? (
            <div className="continuous-pages" style={readerStyle}>
              {sections.map((section) => <article className="reading-paper" id={`section-${section.id}`} key={section.id} data-section-card={section.id}>
                <header><span>{section.page_number ? `PAGE ${section.page_number}` : `SECTION ${section.order_index + 1}`}</span><h1>{section.title}</h1><div /></header>
                <div className="prose">
                  {section.paragraphs.map((paragraph) => <div key={paragraph.id} data-section-id={section.id} data-reader-paragraph-id={paragraph.id} className="paragraph-observer">
                    <ParagraphText paragraph={paragraph} onWord={openSelection} onPhrase={openSelection} />
                  </div>)}
                </div>
                <footer className="page-marker"><span>{section.order_index + 1} / {sections.length}</span></footer>
              </article>)}
            </div>
          ) : <div className="empty-state"><h2>没有可阅读的正文</h2><p>这本书没有提取到有效文字。</p></div>}
        </main>
      </div>

      {pending && <WordModal
        selectedText={pending.text}
        sentence={pending.sentence}
        contextualTranslation={pending.translation?.contextual_translation ?? ''}
        meanings={pending.translation?.meanings ?? []}
        previewing={previewing}
        saving={saving}
        error={modalError}
        onRetry={() => void requestPreview(pending)}
        onSave={() => void saveSelection()}
        onClose={closeModal}
      />}
      {notice && <div className="toast" role="status">{notice}</div>}
    </div>
  )
}
