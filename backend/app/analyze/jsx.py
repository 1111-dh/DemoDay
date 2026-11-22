"""JSX 태그를 정규식만으로 자를 때 생기는 `onClick={() => …}` 같은 `>` 오인식을 피하는 스캐너."""

from __future__ import annotations


def tag_end(src: str, i: int) -> tuple[int, bool]:
    """태그 이름 바로 뒤 i부터 태그 끝 `>`까지 → (끝 다음 위치, self-closing).

    속성의 `{…}`·따옴표 안 `>`는 무시한다.
    """
    depth, quote = 0, ""
    for j in range(i, len(src)):
        c = src[j]
        if quote:
            quote = "" if c == quote else quote
        elif c in "\"'`":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == ">" and depth == 0:
            return j + 1, src[j - 1] == "/"
    return len(src), True
