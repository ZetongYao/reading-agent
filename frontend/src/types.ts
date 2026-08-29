export interface SectionSummary {
  id: number
  book_id: number
  title: string
  order_index: number
  page_number: number | null
}

export interface ReadingProgress {
  section_id: number | null
  paragraph_id: number | null
  scroll_ratio: number
}

export interface Book {
  id: number
  title: string
  author: string | null
  original_filename: string
  file_type: string
  status: 'pending' | 'processing' | 'complete' | 'failed'
  error_message: string | null
  total_pages: number
  processed_pages: number
  char_count: number
  ocr_pages: number
  failed_pages: number[]
  created_at: string
  section_count?: number
  sections?: SectionSummary[]
  progress?: ReadingProgress | null
}

export interface Annotation {
  id: number
  book_id: number
  paragraph_id: number
  start_offset: number
  end_offset: number
  selected_text: string
  chinese_annotation: string
  all_chinese_meanings: string[]
  sentence: string
  page_or_chapter: string
  created_at: string
  existing?: boolean
}

export interface Paragraph {
  id: number
  book_id: number
  section_id: number
  order_index: number
  text: string
  page_number: number | null
  annotations: Annotation[]
}

export interface Section extends SectionSummary {
  paragraphs: Paragraph[]
}

export interface BookContent {
  book_id: number
  sections: Section[]
}

export interface TranslationPreview {
  contextual_translation: string
  meanings: string[]
  cache_hit?: boolean
  cache_scope?: 'exact' | 'term' | 'vocabulary' | 'generated'
}

export interface VocabularyEntry {
  id: number
  annotation_id: number
  selected_text: string
  chinese_annotation: string
  all_chinese_meanings: string[]
  sentence: string
  created_at: string
}

export interface AppSettings {
  ollama_url: string
  ollama_model: string
  theme: 'light' | 'dark'
  font_size: number
  line_height: number
}
