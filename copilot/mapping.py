"""Suggest which of the designer's paragraph styles plays each Galley role.

Pure name matching with weights: a designer's "A Head" is very likely the section heading, "Example Text" the
example body, and so on. The copilot shows the guess with a confidence; the designer confirms or changes it.
The confirmed mapping is stored in the document (label "galley_map"), so the next chapter needs no setup.
"""
import re

# role -> (label shown to the designer, required?, keyword patterns in priority order)
ROLES = [
    ('chapter_label', 'Chapter number line', False, [r'chapter (no|num)', r'chap.*(no|num)', r'unit (no|num)', r'chapter label']),
    ('chapter_title', 'Chapter title', True, [r'chapter (head|title)', r'chap.*(head|title)', r'^title', r'unit (head|title)', r'^h1\b', r'head(ing)? ?1\b']),
    ('objectives_head', 'Objectives heading', False, [r'objective.*(head|title)', r'learn.*head', r'outcome.*head']),
    ('objective', 'Objective item', False, [r'objective', r'outcome', r'learn']),
    ('h2', 'Section heading', True, [r'^a[ -]?head', r'^h2\b', r'head(ing)? ?2\b', r'section', r'^head(ing)?$']),
    ('h3', 'Sub heading', False, [r'^b[ -]?head', r'^h3\b', r'head(ing)? ?3\b', r'sub ?head']),
    ('body', 'Body text', True, [r'^body', r'body text', r'^text$', r'^normal', r'^para', r'main text']),
    ('list', 'Bullet list', False, [r'bullet', r'^list', r'list item']),
    ('figure', 'Figure (picture line)', False, [r'^fig(ure)?$', r'^fig\b', r'picture', r'image', r'graphic']),
    ('caption', 'Caption', False, [r'caption']),
    ('table_head', 'Table header cell', False, [r'table.*head', r'th\b']),
    ('table_body', 'Table body cell', False, [r'table.*(body|text|cell)', r'^table']),
    ('note', 'Note / tip box', False, [r'^tip', r'note', r'did you know', r'callout', r'remember', r'fact']),
    ('example_head', 'Example box heading', True, [r'example.*(head|title)', r'worked.*(head|title)', r'^example$']),
    ('example_body', 'Example box text', True, [r'example.*(text|body)', r'worked.*(text|body)']),
    ('example_step', 'Example step (Question:/Answer:)', False, [r'example.*step', r'step']),
    ('activity_head', 'Activity heading', False, [r'activit.*(head|title)', r'investigat.*(head|title)']),
    ('activity_body', 'Activity text', False, [r'activit.*(text|body)', r'investigat.*(text|body)']),
    ('exercise_head', 'Exercise heading', True, [r'exercise.*(head|title)', r'practi[cs]e.*(head|title)', r'^exercise$', r'quiz.*(head|title)']),
    ('exercise_instruction', 'Exercise instruction', False, [r'exercise.*(instr|direction|text|body)', r'instruction', r'direction']),
    ('question', 'Question', True, [r'exercise ?q\b', r'question', r'^q\b', r'exercise.*(item|q)']),
    ('options', 'Answer options (a)(b)(c)', False, [r'option', r'choice', r'answer.*opt']),
    ('answer_line', 'Answer line', False, [r'answer.*line', r'write.*line', r'^line']),
    ('numbered_list', 'Numbered list', False, [r'number(ed)? ?list', r'^num', r'ordered']),
    ('calc', 'Calculation lines', False, [r'calc', r'working', r'sum\b', r'math']),
    ('rule_head', 'Rule heading ("Addition Rule")', False, [r'rule.*(head|title)', r'^rule$']),
    ('rule_body', 'Rule text', False, [r'rule.*(text|body)']),
    ('teaching_note', 'Teaching note', False, [r'teach', r'teacher']),
]
CHAR_ROLES = [
    ('note_label', 'Note label ("Tip:")', [r'label', r'note.*(label|head)', r'bold']),
    ('step_label', 'Step label ("Answer:")', [r'label', r'step', r'bold']),
    ('question_number', 'Question number', [r'(q|question).*(num|no)', r'number']),
]


def _score(name, patterns):
    n = name.lower().replace('_', ' ')
    for rank, p in enumerate(patterns):
        if re.search(p, n):
            return 1.0 - rank * 0.12
    return 0.0


def suggest(paragraph_styles, character_styles=(), current=None):
    """Return [{role, label, required, style, confidence}] plus character-style suggestions."""
    current = current or {}
    taken = {}
    out = []
    for role, label, req, pats in ROLES:
        if current.get(role) in paragraph_styles:
            out.append({'role': role, 'label': label, 'required': req, 'style': current[role], 'confidence': 1.0, 'source': 'saved'})
            continue
        best, score = '', 0.0
        for s in paragraph_styles:
            sc = _score(s, pats) - (0.3 if s in taken else 0)
            if sc > score:
                best, score = s, sc
        if score > 0.35:
            taken[best] = role
        else:
            best, score = '', 0.0
        out.append({'role': role, 'label': label, 'required': req, 'style': best, 'confidence': round(score, 2), 'source': 'guess' if best else 'none'})
    chars = []
    for role, label, pats in CHAR_ROLES:
        if current.get(role) in character_styles:
            chars.append({'role': role, 'label': label, 'style': current[role], 'confidence': 1.0})
            continue
        best, score = '', 0.0
        for s in character_styles:
            sc = _score(s, pats)
            if sc > score:
                best, score = s, sc
        chars.append({'role': role, 'label': label, 'style': best if score > 0.35 else '', 'confidence': round(score, 2)})
    return {'paragraph': out, 'character': chars}
