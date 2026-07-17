"""Braille-based glucose chart renderer for Textual TUI."""

from rich.text import Text
from rich.style import Style

_BRAILLE_DOTS = [
    (0, 0, 0x01),
    (0, 1, 0x02),
    (0, 2, 0x04),
    (0, 3, 0x40),
    (1, 0, 0x08),
    (1, 1, 0x10),
    (1, 2, 0x20),
    (1, 3, 0x80),
]

MGDL_LABELS = [350, 300, 250, 200, 150, 100, 50]
MMOL_LABELS = [19.4, 16.7, 13.9, 11.1, 8.3, 5.6, 2.8]


def _braille_char(dot_bits):
    return chr(0x2800 | (dot_bits & 0xFF))


def _bresenham(x0, y0, x1, y1):
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy_ = 1 if y0 < y1 else -1
    err = dx - dy
    x, y = x0, y0
    while True:
        yield x, y
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy_


def _interp_value(x_sub, values, total_sub_cols):
    n = len(values)
    if n < 2:
        return values[0] if values else 0
    t = x_sub / max(total_sub_cols - 1, 1)
    idx = t * (n - 1)
    i0 = int(idx)
    i1 = min(i0 + 1, n - 1)
    frac = idx - i0
    return values[i0] * (1.0 - frac) + values[i1] * frac


def render_chart(
    values,
    timestamps=None,
    width=40,
    height=7,
    low_threshold=70,
    high_threshold=180,
    use_mmol=False,
    theme=None,
):
    n = len(values)
    if n < 2 or width < 4:
        return Text("")

    theme = theme or {}
    low_color = theme.get("low", "#f38ba8")
    high_color = theme.get("high", "#fab387")
    normal_color = theme.get("normal", "#a6e3a1")
    muted_color = theme.get("muted", "#585b70")

    if use_mmol:
        conv = 18.0182
        lo_thresh = round(low_threshold / conv, 1)
        hi_thresh = round(high_threshold / conv, 1)
        y_labels_display = MMOL_LABELS
    else:
        lo_thresh = low_threshold
        hi_thresh = high_threshold
        y_labels_display = MGDL_LABELS

    y_lo, y_hi = 0, 350
    y_range = y_hi - y_lo
    sub_rows = height * 4
    sub_cols = width * 2

    def value_to_sub_y(val):
        return round((y_hi - val) / y_range * (sub_rows - 1))

    data_points = []
    for i, v in enumerate(values):
        sx = round(i / max(n - 1, 1) * (sub_cols - 1))
        sy = value_to_sub_y(v)
        sy = max(0, min(sub_rows - 1, sy))
        data_points.append((sx, sy))

    trace = set()
    for i in range(n - 1):
        x0, y0 = data_points[i]
        x1, y1 = data_points[i + 1]
        for px, py in _bresenham(x0, y0, x1, y1):
            trace.add((px, py))

    guide_rows = set()
    for threshold in (low_threshold, high_threshold):
        sy = value_to_sub_y(threshold)
        sy = max(0, min(sub_rows - 1, sy))
        gr = sy // 4
        if gr % 2 != 0:
            gr = max(0, gr - 1)
        guide_rows.add(gr)

    braille_rows = []
    for row in range(height):
        cells = []
        cell_styles = []
        for col in range(width):
            dot_bits = 0
            has_trace = False
            for sc, sr, mask in _BRAILLE_DOTS:
                sx = col * 2 + sc
                sy = row * 4 + sr
                if (sx, sy) in trace:
                    dot_bits |= mask
                    has_trace = True

            if dot_bits:
                ch = _braille_char(dot_bits)
            else:
                ch = " "

            cells.append(ch)

            if has_trace:
                val = _interp_value(col * 2 + 1, values, sub_cols)
                if use_mmol:
                    val = val / 18.0182
                if val < lo_thresh:
                    style = Style(color=low_color)
                elif val > hi_thresh:
                    style = Style(color=high_color)
                else:
                    style = Style(color=normal_color)
            else:
                style = Style(color=muted_color)

            cell_styles.append(style)

        braille_rows.append((cells, cell_styles))

    label_width = 4 if use_mmol else 3
    y_labels = []
    for r in range(height):
        if r % 2 == 0:
            idx = r // 2
            label = y_labels_display[idx] if idx < len(y_labels_display) else ""
            y_labels.append(f"{label:>{label_width}}")
        else:
            y_labels.append(" " * label_width)

    x_label_line = ""
    if timestamps and len(timestamps) == n:
        times = [t.astimezone().strftime("%H:00") for t in timestamps]

        indent = " " * (label_width + 1)
        x_buf = indent
        last_end = 0

        x_buf += times[0]
        last_end = len(times[0])

        for i in range(1, n - 1):
            col = round(i / max(n - 1, 1) * width)
            lw = len(times[i])
            gap = col - last_end
            if gap >= 1:
                x_buf += " " * gap + times[i]
                last_end = col + lw

        last_col = round((n - 1) / max(n - 1, 1) * width)
        gap = last_col - last_end
        if gap >= 1:
            x_buf += " " * gap + times[-1]

        x_label_line = x_buf

    lines = []
    for r in range(height):
        line = Text()
        line.append(y_labels[r], style=Style(color=muted_color))
        if r in guide_rows:
            line.append("│", style=Style(color=muted_color))
        else:
            line.append(" ")
        cells, styles = braille_rows[r]
        for ch, st in zip(cells, styles):
            line.append(ch, style=st)
        lines.append(line)

    if x_label_line:
        lines.append(Text(x_label_line, style=Style(color=muted_color)))

    return Text("\n").join(lines)
