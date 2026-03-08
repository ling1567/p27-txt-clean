import regex as re
import charset_normalizer
from typing import BinaryIO, Generator, List, Union, Dict, Any
import html

# Built-in patterns for common chapter headers
BUILT_IN_CHAPTER_PATTERNS = [
    r'^第[一二三四五六七八九十百千万零\d]+[章节回卷折篇幕]\s*.*$',
    r'^(?i)Chapter\s*\d+.*$',
    r'^(?i)Section\s*\d+.*$',
    r'^[IVXLCDM]+\.?\s*.*$', # Roman numerals
    r'^\s*\d+\s+.*$' # Simple numbered headers like "1. Title"
]

def detect_encoding(file_obj: BinaryIO) -> str:
    """Detect encoding of a binary file stream."""
    file_obj.seek(0)
    sample = file_obj.read(1024 * 1024)
    file_obj.seek(0)
    
    results = charset_normalizer.from_bytes(sample)
    if not results:
        return "utf-8"
    
    best_match = results.best()
    if not best_match:
        return "utf-8"
    
    return best_match.encoding

def remove_bom(text: str) -> str:
    """Remove BOM (Byte Order Mark) from a string if present."""
    if text.startswith('\ufeff'):
        return text[1:]
    return text

def normalize_line_breaks(text: str) -> str:
    """Normalize Windows (\r\n) and Mac (\r) line breaks to Unix (\n)."""
    return text.replace('\r\n', '\n').replace('\r', '\n')

def clean_control_characters(text: str) -> str:
    """Remove C0/C1 control characters (except \n, \r, \t) and invisible characters."""
    control_pattern = r'(?![\r\n\t])\p{Cc}'
    text = re.sub(control_pattern, '', text)
    invisible_pattern = r'[\u200B\u200C\u200D\uFEFF]'
    text = re.sub(invisible_pattern, '', text)
    text = text.replace('\uFFFD', '')
    text = text.replace('\u00A0', ' ')
    return text

def remove_html_tags(text: str) -> str:
    """Simple HTML/XML tag removal."""
    text = re.sub(r'<[^>]+>', '', text)
    return html.unescape(text)

def clean_paragraph(text: str) -> str:
    """Trim leading and trailing whitespace from each line."""
    lines = text.split('\n')
    cleaned_lines = [line.strip() for line in lines]
    return '\n'.join(cleaned_lines)

def compress_empty_lines(text: str, threshold: int = 2) -> str:
    """Compress consecutive empty lines to a maximum of 'threshold'."""
    if threshold < 0:
        return text
        
    lines = text.split('\n')
    processed_lines = []
    for line in lines:
        if not line.strip():
            processed_lines.append('')
        else:
            processed_lines.append(line)
            
    result = []
    empty_count = 0
    for line in processed_lines:
        if line == '':
            empty_count += 1
            if empty_count <= threshold:
                result.append(line)
        else:
            empty_count = 0
            result.append(line)
            
    return '\n'.join(result)

def identify_chapters(text: str, config: Any) -> List[Dict[str, Any]]:
    """Identify chapters in the text based on patterns and line length."""
    chapters = []
    lines = text.split('\n')
    
    patterns = []
    if config.chapter.built_in_patterns:
        patterns.extend(BUILT_IN_CHAPTER_PATTERNS)
    if config.chapter.custom_regex:
        patterns.append(config.chapter.custom_regex)
        
    max_title_len = 35 # Configurable threshold
    
    for i, line in enumerate(lines):
        clean_line = line.strip()
        if not clean_line or len(clean_line) > max_title_len:
            continue
            
        is_chapter = False
        for pattern in patterns:
            try:
                if re.match(pattern, clean_line):
                    is_chapter = True
                    break
            except Exception:
                continue # Ignore invalid regex
        
        if is_chapter:
            chapters.append({
                "title": clean_line,
                "line_index": i,
                "original_order": len(chapters) + 1
            })
            
    return chapters

def process_chunk(chunk: str, config: Any) -> str:
    """Apply Stage 1 & 2 cleaning rules to a text chunk."""
    text = normalize_line_breaks(chunk)
    
    if config.base_cleaning.remove_html:
        text = remove_html_tags(text)
    
    if config.base_cleaning.remove_control_chars:
        text = clean_control_characters(text)
        
    for pattern in config.base_cleaning.manual_blacklists:
        if pattern:
            text = text.replace(pattern, '')
            
    text = clean_paragraph(text)
    text = compress_empty_lines(text, config.formatting.empty_line_threshold)
            
    return text
