import type { Annotation, AppSettings, Book, BookContent, Section, TranslationPreview, VocabularyEntry } from './types'

export const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, options)
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const payload = await response.json()
      message = typeof payload.detail === 'string' ? payload.detail : message
    } catch {
      // Keep the HTTP fallback message.
    }
    throw new ApiError(response.status, message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

const jsonOptions = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

const translationRequests = new Map<string, Promise<TranslationPreview>>()

function previewTranslation(selectedText: string, sentence: string) {
  const key = `${selectedText.trim().toLocaleLowerCase()}\u0000${sentence.trim().toLocaleLowerCase()}`
  const existing = translationRequests.get(key)
  if (existing) return existing
  const pending = request<TranslationPreview>('/translations/preview', jsonOptions('POST', {
    selected_text: selectedText,
    sentence,
  }))
  translationRequests.set(key, pending)
  pending.then(
    () => {
      if (translationRequests.get(key) === pending) translationRequests.delete(key)
    },
    () => {
      translationRequests.delete(key)
    },
  )
  return pending
}

export const api = {
  books: () => request<Book[]>('/books'),
  book: (id: number) => request<Book>(`/books/${id}`),
  section: (id: number) => request<Section>(`/sections/${id}`),
  bookContent: (id: number) => request<BookContent>(`/books/${id}/content`),
  upload: async (file: File) => {
    const data = new FormData()
    data.append('file', file)
    return request<{ id: number; status: string; message: string }>('/books', { method: 'POST', body: data })
  },
  deleteBook: (id: number) => request<void>(`/books/${id}`, { method: 'DELETE' }),
  searchBook: (id: number, query: string) =>
    request<Array<{ paragraph_id: number; section_id: number; text: string; section_title: string; page_number: number | null }>>(
      `/books/${id}/search?q=${encodeURIComponent(query)}`,
    ),
  saveProgress: (bookId: number, body: { section_id: number; paragraph_id: number | null; scroll_ratio: number }) =>
    request(`/books/${bookId}/progress`, jsonOptions('PUT', body)),
  annotate: (body: {
    book_id: number
    paragraph_id: number
    start_offset: number
    end_offset: number
    selected_text: string
    chinese_annotation: string
    all_chinese_meanings: string[]
  }) => request<Annotation>('/annotations', jsonOptions('POST', body)),
  previewTranslation,
  vocabulary: (search = '') => {
    const params = new URLSearchParams()
    if (search) params.set('search', search)
    return request<VocabularyEntry[]>(`/vocabulary?${params}`)
  },
  updateVocabulary: (id: number, chinese_annotation: string) =>
    request<VocabularyEntry>(`/vocabulary/${id}`, jsonOptions('PATCH', { chinese_annotation })),
  deleteVocabulary: (id: number) => request<void>(`/vocabulary/${id}`, { method: 'DELETE' }),
  settings: () => request<AppSettings>('/settings'),
  updateSettings: (body: Partial<AppSettings>) => request<AppSettings>('/settings', jsonOptions('PUT', body)),
  checkOllama: () =>
    request<{ running: boolean; model_installed: boolean; model: string; message: string }>('/ollama/check', {
      method: 'POST',
    }),
}
