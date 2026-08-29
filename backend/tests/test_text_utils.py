from backend.app.text_utils import sentence_at, split_paragraphs


def test_sentence_at_handles_quotes_and_multiple_sentences():
    text = 'He said, "Stay curious." The company changed quickly! Why now?'
    start = text.index("company")
    assert sentence_at(text, start, start + 7) == "The company changed quickly!"


def test_split_paragraphs_keeps_original_words():
    assert split_paragraphs("First line\ncontinues here.\n\nSecond paragraph.") == [
        "First line continues here.",
        "Second paragraph.",
    ]

