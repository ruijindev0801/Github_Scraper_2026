"""
Solution to the Google Doc grid decoding exercise.

Takes a published Google Doc URL containing a 3-column table
(x-coordinate, character, y-coordinate) and prints the grid the
characters form, with empty cells rendered as spaces.
"""

import re
import urllib.request


def print_grid_from_doc(url: str) -> None:
    with urllib.request.urlopen(url, timeout=20) as response:
        html = response.read().decode("utf-8", errors="ignore")

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.DOTALL)
    grid: dict[tuple[int, int], str] = {}
    max_x = max_y = 0

    for row_html in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, flags=re.DOTALL)
        if len(cells) < 3:
            continue
        texts = [re.sub(r"<[^>]+>", "", c).replace("&nbsp;", " ").strip() for c in cells]
        try:
            x = int(texts[0])
            ch = texts[1]
            y = int(texts[2])
        except (ValueError, IndexError):
            continue
        if not ch:
            continue
        grid[(x, y)] = ch
        if x > max_x:
            max_x = x
        if y > max_y:
            max_y = y

    # The example F shows (0, 0) at the bottom-left corner (y increases upward),
    # so render with the highest y at the top of the image.
    for y in range(max_y, -1, -1):
        line = "".join(grid.get((x, y), " ") for x in range(max_x + 1))
        print(line.rstrip())


if __name__ == "__main__":
    URL = (
        "https://docs.google.com/document/d/e/2PACX-1vSvM5gDlNvt7npYHhp_"
        "XfsJvuntUhq184By5xO_pA4b_gCWeXb6dM6ZxwN8rE6S4ghUsCj2VKR21oEP/pub"
    )
    print_grid_from_doc(URL)
