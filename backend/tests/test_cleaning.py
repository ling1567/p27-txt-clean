import pytest
import io
from backend.core.cleaning import remove_bom, normalize_line_breaks, clean_control_characters, remove_html_tags, detect_encoding, clean_paragraph, compress_empty_lines

def test_clean_paragraph():
    test_str = "  Line 1  \n\tLine 2\n  Line 3  "
    assert clean_paragraph(test_str) == "Line 1\nLine 2\nLine 3"

def test_compress_empty_lines():
    # Threshold = 1
    test_str = "L1\n\n\nL2\n\nL3"
    assert compress_empty_lines(test_str, 1) == "L1\n\nL2\n\nL3"
    
    # Threshold = 0 (compact)
    assert compress_empty_lines(test_str, 0) == "L1\nL2\nL3"
    
    # Threshold = 2 (default)
    test_str_2 = "L1\n\n\n\nL2"
    assert compress_empty_lines(test_str_2, 2) == "L1\n\n\nL2"

def test_detect_encoding():
    # ASCII/UTF-8
    utf8_data = "Hello World".encode("utf-8")
    detected = detect_encoding(io.BytesIO(utf8_data)).lower().replace("_", "-")
    assert detected in ["utf-8", "ascii", "us-ascii"]
    
    # GBK
    gbk_data = "你好".encode("gbk")
    # charset-normalizer might return 'cp936' for gbk, which is compatible
    detected = detect_encoding(io.BytesIO(gbk_data)).lower()
    assert detected in ["gbk", "cp936", "gb18030", "big5"]

def test_remove_bom():
    # \uFEFF is the UTF-8 BOM character
    assert remove_bom("\uFEFFHello World") == "Hello World"
    assert remove_bom("Hello World") == "Hello World"

def test_normalize_line_breaks():
    # Windows style (\r\n) and old Mac style (\r) to Unix (\n)
    test_str = "Line 1\r\nLine 2\rLine 3\nLine 4"
    assert normalize_line_breaks(test_str) == "Line 1\nLine 2\nLine 3\nLine 4"

def test_clean_control_characters():
    # Keep \n (0x0A), \r (0x0D), \t (0x09)
    # \x00 is null, \x08 is backspace
    original = "Hello\x00World\nTabs\tReturn\rControl\x08End"
    cleaned = clean_control_characters(original)
    assert cleaned == "HelloWorld\nTabs\tReturn\rControlEnd"
    
    # Invisible characters
    assert clean_control_characters("Zero\u200BWidth\u200CSpace") == "ZeroWidthSpace"
    assert clean_control_characters("Joiner\u200D") == "Joiner"
    
    # FFFD replacement
    assert clean_control_characters("Error\uFFFDChar") == "ErrorChar"
    
    # Non-breaking space
    assert clean_control_characters("Non\u00A0Breaking") == "Non Breaking"

def test_remove_html_tags():
    assert remove_html_tags("<div>Hello <b>World</b></div>") == "Hello World"
    # Note: html.unescape("&nbsp;") returns "\xa0" which is non-breaking space
    text = remove_html_tags("Hello &nbsp; World &amp; More")
    assert "World & More" in text
    
    # Testing the combination:
    cleaned_text = clean_control_characters(text)
    assert cleaned_text == "Hello   World & More"
