from __future__ import annotations


DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 200


def _find_boundary(text: str, start: int, target_end: int, overlap: int) -> int:
    lower_bound = min(len(text), start + max(DEFAULT_CHUNK_SIZE // 2, overlap + 1))
    if target_end <= lower_bound:
        return target_end

    paragraph_break = text.rfind("\n\n", lower_bound, target_end)
    if paragraph_break != -1:
        return paragraph_break + 2

    sentence_break = max(
        text.rfind(". ", lower_bound, target_end),
        text.rfind("? ", lower_bound, target_end),
        text.rfind("! ", lower_bound, target_end),
    )
    if sentence_break != -1:
        return sentence_break + 2

    whitespace_break = text.rfind(" ", lower_bound, target_end)
    if whitespace_break != -1:
        return whitespace_break + 1

    return target_end


def chunk_text(
    text: str,
    target_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[dict[str, int | str]]:
    if not text:
        return []

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    chunks: list[dict[str, int | str]] = []
    start = 0

    while start < len(normalized):
        proposed_end = min(len(normalized), start + target_size)
        if proposed_end >= len(normalized):
            end = len(normalized)
        else:
            end = _find_boundary(normalized, start, proposed_end, overlap)
            if end <= start:
                end = proposed_end

        raw_chunk = normalized[start:end]
        leading_ws = len(raw_chunk) - len(raw_chunk.lstrip())
        trailing_ws = len(raw_chunk) - len(raw_chunk.rstrip())
        content = raw_chunk.strip()

        if content:
            chunk_start = start + leading_ws
            chunk_end = end - trailing_ws
            chunks.append(
                {
                    "chunk_index": len(chunks),
                    "content": content,
                    "char_start": chunk_start,
                    "char_end": chunk_end,
                }
            )

        if end >= len(normalized):
            break

        next_start = max(end - overlap, start + 1)
        while next_start < len(normalized) and normalized[next_start].isspace():
            next_start += 1
        start = next_start

    return chunks
