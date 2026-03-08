import regex as re
import html
from typing import Callable, Optional

def normalize_newlines(text: str) -> str:
    return text.replace('\r\n', '\n').replace('\r', '\n')

def filter_illegal_characters(text: str) -> str:
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]', '', text)
    text = re.sub(r'[\u200B-\u200D\uFEFF]', '', text)
    text = text.replace('\u00A0', ' ')
    text = text.replace('\uFFFD', '')
    return text

def clean_html(text: str) -> str:
    text = html.unescape(text)
    text = re.sub(r'<[^>]+>', '', text)
    return text

def convert_full_half_width(text: str, convert_alnum: bool = True, convert_punct: bool = True) -> str:
    if convert_alnum:
        def to_half(m):
            return chr(ord(m.group(0)) - 0xFEE0)
        text = re.sub(r'[\uFF10-\uFF19\uFF21-\uFF3A\uFF41-\uFF5A]', to_half, text)

    if convert_punct:
        punct_map = {
            ',': '，', '.': '。', '?': '？', '!': '！',
            ':': '：', ';': '；', '(': '（', ')': '）',
            '[': '【', ']': '】'
        }
        for p, full_p in punct_map.items():
            def replace_func(m):
                pos = m.start()
                prev_char = text[pos-1] if pos > 0 else ""
                next_char = text[pos+1] if pos < len(text) - 1 else ""
                if prev_char.isalnum() and next_char.isalnum():
                    return p 
                return full_p
            text = re.sub(re.escape(p), replace_func, text)
    return text

def stitch_broken_sentences(text: str, min_line_length: int = 15) -> str:
    lines = text.split('\n')
    if not lines:
        return text
    terminators = ('。', '！', '？', '”', '」', '…', '~', ':', '：', '>', '》')
    opening_quotes = ('“', '「', '《', '<', '（', '(')
    processed_lines = []
    i = 0
    while i < len(lines):
        current_line = lines[i]
        if i == len(lines) - 1:
            processed_lines.append(current_line)
            break
        next_line = lines[i+1]
        curr_stripped = current_line.strip()
        next_stripped = next_line.strip()
        should_stitch = False
        if len(curr_stripped) >= min_line_length:
            if curr_stripped and curr_stripped[-1] not in terminators:
                if next_stripped and next_stripped[0] not in opening_quotes:
                    if not next_line.startswith(('  ', '\t', '\u3000')) or next_stripped[0] in ('，', '。', '？', '！', '”', '」'):
                        should_stitch = True
        if should_stitch:
            spacer = ""
            if curr_stripped and next_stripped:
                if curr_stripped[-1].isascii() and curr_stripped[-1].isalnum() and \
                   next_stripped[0].isascii() and next_stripped[0].isalnum():
                    spacer = " "
            lines[i+1] = current_line + spacer + next_line.lstrip()
            i += 1
        else:
            processed_lines.append(current_line)
            i += 1
    return '\n'.join(processed_lines)

def trim_paragraphs(text: str, add_indent: bool = False) -> str:
    lines = text.split('\n')
    processed_lines = []
    for line in lines:
        trimmed = line.strip(' \t\u3000')
        if trimmed and add_indent:
            trimmed = '\u3000\u3000' + trimmed
        processed_lines.append(trimmed)
    return '\n'.join(processed_lines)

def compress_empty_lines(text: str, threshold: int = 2) -> str:
    lines = text.split('\n')
    cleaned_lines = [line if line.strip(' \t\u3000') else '' for line in lines]
    text = '\n'.join(cleaned_lines)
    pattern = r'\n{' + str(threshold + 1) + r',}'
    replacement = '\n' * threshold
    return re.sub(pattern, replacement, text)

def filter_manual_blacklist(text: str, blacklist: list[str]) -> str:
    if not blacklist:
        return text
    pattern = '[' + re.escape(''.join(blacklist)) + ']'
    return re.sub(pattern, '', text)

def clean_text_pipeline(text: str, options: dict, progress_callback: Optional[Callable[[int], None]] = None) -> tuple[str, list[str]]:
    """核心清洗流水线，带进度反馈"""
    logs = []
    steps = [
        ('manualIllegal', lambda t: filter_manual_blacklist(t, options.get('manual_blacklist', [])), "手动定义黑名单过滤"),
        ('newline', lambda t: normalize_newlines(t), "换行符归一化 (LF)"),
        ('html', lambda t: clean_html(t), "HTML 标签清理与实体反转义"),
        ('illegal', lambda t: filter_illegal_characters(t), "非法字符过滤"),
        ('fullwidth', lambda t: convert_full_half_width(t), "全半角转换"),
        ('stitch', lambda t: stitch_broken_sentences(t), "断句缝合"),
        ('paragraph', lambda t: trim_paragraphs(t), "段落清洗"),
        ('emptyline', lambda t: compress_empty_lines(t, threshold=2), "空行压缩"),
    ]
    
    total_steps = len([s for s in steps if options.get(s[0], s[0] == 'newline')])
    current_step = 0
    
    for opt_key, func, log_msg in steps:
        if options.get(opt_key, opt_key == 'newline'):
            text = func(text)
            logs.append(f"已完成{log_msg}")
            current_step += 1
            if progress_callback:
                progress_callback(int((current_step / total_steps) * 100))
                
    return text, logs
