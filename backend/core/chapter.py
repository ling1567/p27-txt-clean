import regex as re
from typing import List, Dict, Any, Optional

# 数字宏：匹配中文数字和阿拉伯数字
NUM_MACRO = r'[一二三四五六七八九十百千万零〇\d]+'
FULL_WIDTH_NUM = r'[０-９]+'

# 核心自动识别正则库
AUTO_PATTERNS = [
    # 1. 传统标准型
    rf'^第\s*{NUM_MACRO}\s*[章节回]\s*(.*)$',
    rf'^第\s*{NUM_MACRO}\s*[卷部篇折]\s*(.*)$',
    rf'^(?:正文|VIP卷|VIP章节)?\s*第\s*{NUM_MACRO}\s*[章节回]\s*(.*)$',
    
    # 2. 极简西方型
    r'^\s*\d+(?:\.\d+)?\s*[\.、]\s*(.*)$',
    rf'^\s*(?:Chapter|Ch|Part|Vol|Episode)\.?\s*{NUM_MACRO}\s*[:\-\s]\s*(.*)$',
    rf'^\s*{FULL_WIDTH_NUM}\s+(.*)$',
    
    # 3. 符号装饰型
    rf'^\s*[【\[]\s*(?:第\s*)?{NUM_MACRO}\s*[章节回]?\s*[】\]]\s*(.*)$',
    rf'^\s*[☆★◆◇■□]\s*(?:第\s*)?{NUM_MACRO}\s*[章节回卷]\s*[☆★◆◇■□]\s*(.*)$',
    rf'^\s*[~\-]{{2,}}\s*第\s*{NUM_MACRO}\s*[章节回]\s*[~\-]{{2,}}\s*(.*)$',
    
    # 4. 独立词汇型
    r'^\s*(?:序|序章|序言|引子|楔子|前言)\s*(.*)$',
    r'^\s*(?:尾声|终章|后记|番外(?:篇)?|附录|大结局|完本感言)\s*(.*)$',
    
    # 5. 危险兜底型
    r'^\s*\d+\s*$'
]

def detect_chapters(text: str, custom_pattern: Optional[str] = None, max_length: int = 35) -> List[Dict[str, Any]]:
    """识别章节并返回结构化数据"""
    lines = text.split('\n')
    chapters = []
    
    # 使用自定义正则或内置正则库
    patterns = [custom_pattern] if custom_pattern and custom_pattern.strip() else AUTO_PATTERNS
    
    for idx, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped or len(line_stripped) > max_length:
            continue
            
        for p in patterns:
            try:
                reg = re.compile(p)
                match = reg.match(line_stripped)
                if match:
                    # 尝试寻找序号组（通常是第一个捕获组，如果没捕获组则取整行）
                    raw_num = match.group(1) if match.groups() else line_stripped
                    
                    # 计算偏移量用于物理替换
                    start_in_original = line.find(line_stripped)
                    if start_in_original == -1: start_in_original = 0
                    
                    # 记录位置（如果有捕获组，记录第一个组的位置；否则记录全行）
                    if match.groups():
                        start, end = match.span(1)
                    else:
                        start, end = 0, len(line_stripped)
                    
                    chapters.append({
                        "index": len(chapters) + 1,
                        "title": line_stripped,
                        "line_number": idx,
                        "span": (start_in_original + start, start_in_original + end),
                        "raw_num": raw_num,
                        "pattern": p
                    })
                    break
            except Exception:
                continue
    return chapters

def auto_detect_chapter_pattern(text: str, sample_size: int = 1000) -> Optional[str]:
    """矩阵轰炸式识别：抽取前N行，寻找命中率最高且具备数字递增特征的正则"""
    lines = text.split('\n')[:sample_size]
    best_pattern = None
    max_hits = 0
    
    for p in AUTO_PATTERNS:
        hits = 0
        try:
            reg = re.compile(p)
            for line in lines:
                if 0 < len(line.strip()) <= 35 and reg.match(line.strip()):
                    hits += 1
            
            # 基础阈值：至少命中 2 次才考虑
            if hits >= 2 and hits > max_hits:
                max_hits = hits
                best_pattern = p
        except Exception:
            continue
            
    return best_pattern

def reorder_chapters(text: str, chapters: List[Dict[str, Any]]) -> str:
    """基于物理位置精确替换章节序号"""
    lines = text.split('\n')
    for i, ch in enumerate(chapters):
        line_idx = ch["line_number"]
        original_line = lines[line_idx]
        new_index = str(i + 1)
        start, end = ch["span"]
        new_line = original_line[:start] + new_index + original_line[end:]
        lines[line_idx] = new_line
    return '\n'.join(lines)

def deduce_regex(samples: List[str]) -> str:
    """从样本推导正则表达式"""
    if not samples: return ""
    sample = samples[0].strip()
    match = re.search(r'[0-9]+', sample)
    replacement = r'(\d+)'
    if not match:
        match = re.search(r'[一二三四五六七八九十百千万零]+', sample)
        replacement = r'([一二三四五六七八九十百千万零]+)'
    if not match: return ""
    start, end = match.span()
    before_esc = re.escape(sample[:start]).replace(r'\ ', r'\s*').replace(' ', r'\s*')
    after_esc = re.escape(sample[end:]).replace(r'\ ', r'\s*').replace(' ', r'\s*')
    return f"^{before_esc}{replacement}{after_esc}.*$"
