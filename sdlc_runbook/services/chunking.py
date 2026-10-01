def split_text(text: str, max_chars: int) -> list[tuple[int, str]]:
    """Split into (offset, chunk) pieces of at most max_chars, breaking at whitespace where possible."""
    chunks, start = [], 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            cut = max(text.rfind(ch, start, end) for ch in (" ", "\n", "\t"))
            if cut > start + max_chars // 2:
                end = cut
        chunks.append((start, text[start:end]))
        start = end
    return chunks
