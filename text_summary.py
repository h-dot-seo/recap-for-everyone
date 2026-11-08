"""ASCII-safe text summaries for CLI --text output; data cannot spoof labels or lines."""
import json


def quoted_display(value):
    """Quote one supplied value as ASCII JSON so no data byte reaches the terminal raw.

    Control, format and line/paragraph separator characters become JSON escapes.
    DEL is escaped explicitly because json leaves that ASCII control character raw.
    Object keys are sorted; the result stays valid JSON for later inspection.
    """
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False)
    return encoded.replace('\x7f', '\\u007f')


def summary_text(header, items):
    """Render code-supplied labels with quoted values, one label per line.

    Labels must come from the program, never from archive or file data. The
    header is one fixed line. Output is ASCII-only and ends with a newline.
    """
    lines = [header]
    for label, value in items:
        lines.append(label + ': ' + quoted_display(value))
    return '\n'.join(lines) + '\n'
