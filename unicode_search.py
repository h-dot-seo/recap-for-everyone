"""Canonical caseless search copies with covering offsets into unchanged evidence."""
import unicodedata


def canonical_fold(text):
    """Use canonical decomposition before folding, then an NFC search copy."""
    return unicodedata.normalize('NFC', unicodedata.normalize('NFD', text).casefold())


def _ordered(items):
    """Stable canonical ordering, buffering only one nonstarter sequence."""
    marks = []
    for item in items:
        if unicodedata.combining(item[0]) == 0:
            yield from sorted(marks, key=lambda value: unicodedata.combining(value[0]))
            marks.clear()
            yield item
        else:
            marks.append(item)
    yield from sorted(marks, key=lambda value: unicodedata.combining(value[0]))


def _decomposed(items, fold=False):
    for character, start, end in items:
        value = character.casefold() if fold else character
        for part in unicodedata.normalize('NFD', value):
            yield part, start, end


def _composed(items):
    """NFC composition, retaining original covering intervals through reordering.

    Ask the runtime's NFC tables for primary composites, including Hangul and
    pairs whose second code point has combining class zero. A retained mark of
    equal or higher class blocks composition; a consumed mark does not.
    """
    pending = []
    starter = False
    last_class = 0
    for character, start, end in items:
        current_class = unicodedata.combining(character)
        if starter and (last_class < current_class or last_class == 0):
            first, first_start, first_end = pending[0]
            composite = unicodedata.normalize('NFC', first + character)
            if len(composite) == 1:
                pending[0] = composite, min(first_start, start), max(first_end, end)
                continue
        if current_class == 0:
            yield from pending
            pending = []
            starter = True
        pending.append((character, start, end))
        last_class = current_class
    yield from pending


def _canonical_items(text):
    """Yield NFC search characters with original half-open code-point spans.

    Both ordering passes matter: U+0345 can move before case folding changes it
    into a starter. Storage depends on the longest combining sequence, not the
    total message length; pathological all-mark inputs can still need O(n).
    """
    original = ((character, index, index + 1) for index, character in enumerate(text))
    decomposed = _ordered(_decomposed(original))
    folded = _ordered(_decomposed(decomposed, fold=True))
    yield from _composed(folded)


def canonical_span(text, start, stop):
    """Map a nonempty normalized interval to its covering original interval."""
    if type(start) is not int or type(stop) is not int or not 0 <= start < stop:
        raise ValueError('canonical match offsets must describe a nonempty interval')
    first, last = None, None
    for position, (_, original_start, original_end) in enumerate(_canonical_items(text)):
        if position >= start:
            first = original_start if first is None else min(first, original_start)
            last = original_end if last is None else max(last, original_end)
        if position + 1 == stop:
            return first, last
    raise ValueError('canonical match offsets exceed normalized text')
