import regex as re
from typing import List, Dict, Any

# 内置通用正则范式 (确保第一个捕获组是数字)
BUILTIN_PATTERNS = [
    r'^第?\s*([0-9０-９一二三四五六七八九十百千万零]+)\s*[章节回].*$',
    r'^(?i:Chapter|Vol|Part)\s*([0-9]+).*$',
    r'^([0-9]+)[\.\s、].*$',
    r'^([IVXLCDM]+)[\.\s、].*$'
]

def detect_chapters(text: str, custom_pattern: str = None, max_length: int = 35) -> List[Dict[str, Any]]:
    """识别章节并返回结构化数据，记录数字的起止位置"""
    lines = text.split('\n')
    chapters = []
    
    # 如果自定义正则为空，则使用内置正则
    patterns = [custom_pattern] if custom_pattern and custom_pattern.strip() else BUILTIN_PATTERNS
    
    for idx, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped or len(line_stripped) > max_length:
            continue
            
        for p in patterns:
            try:
                reg = re.compile(p)
                match = reg.match(line_stripped)
                if match and match.groups():
                    # 找到第一个捕获组 (即序号)
                    # 计算数字在原始行（未 strip 前）中的偏移量
                    # 我们先找到 line_stripped 在 line 中的起始位置
                    start_in_original = line.find(line_stripped)
                    if start_in_original == -1: start_in_original = 0
                    
                    start, end = match.span(1)
                    
                    chapters.append({
                        "index": len(chapters) + 1,
                        "title": line_stripped,
                        "line_number": idx,
                        "span": (start_in_original + start, start_in_original + end),
                        "raw_num": match.group(1),
                        "pattern": p
                    })
                    break
            except Exception as e:
                continue
    return chapters

def reorder_chapters(text: str, chapters: List[Dict[str, Any]]) -> str:
    """基于物理位置精确替换章节序号"""
    lines = text.split('\n')
    
    for i, ch in enumerate(chapters):
        line_idx = ch["line_number"]
        original_line = lines[line_idx]
        new_index = str(i + 1)
        
        start, end = ch["span"]
        # 精确切片替换
        new_line = original_line[:start] + new_index + original_line[end:]
        lines[line_idx] = new_line
            
    return '\n'.join(lines)

def deduce_regex(samples: List[str]) -> str:
    """智能引导模式：从样本推导正则表达式"""
    if not samples:
        return ""
    
    sample = samples[0].strip()
    
    # 1. 寻找数字部分
    match = re.search(r'[0-9]+', sample)
    replacement = r'(\d+)'
    
    if not match:
        match = re.search(r'[一二三四五六七八九十百千万零]+', sample)
        replacement = r'([一二三四五六七八九十百千万零]+)'
        
    if not match:
        return ""
        
    start, end = match.span()
    before = sample[:start]
    after = sample[end:]
    
    # 2. 分别转义并拼接，将空格转义为 \s*
    # 注意：re.escape 在不同 Python 版本行为不同，这里手动处理空格
    before_esc = re.escape(before).replace(r'\ ', r'\s*').replace(' ', r'\s*')
    after_esc = re.escape(after).replace(r'\ ', r'\s*').replace(' ', r'\s*')
    
    # 3. 构造正则
    return f"^{before_esc}{replacement}{after_esc}.*$"
