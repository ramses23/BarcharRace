def estimate_text_width(text, font_size, average_char_width=0.56):
    return len(str(text)) * font_size * average_char_width


def fit_text_to_width(text, max_width, font_size, average_char_width=0.56):
    text = str(text)

    if max_width <= 0:
        return ""

    if estimate_text_width(text, font_size, average_char_width) <= max_width:
        return text

    ellipsis = "..."
    ellipsis_width = estimate_text_width(ellipsis, font_size, average_char_width)

    if ellipsis_width > max_width:
        return ""

    available_width = max_width - ellipsis_width
    char_width = font_size * average_char_width
    max_chars = max(0, int(available_width // char_width))

    if max_chars == 0:
        return ellipsis

    return text[:max_chars].rstrip() + ellipsis
