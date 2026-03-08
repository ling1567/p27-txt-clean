from pydantic import BaseModel, Field
from typing import List, Optional

class EncodingConfig(BaseModel):
    detect: bool = True
    manual_encoding: Optional[str] = None

class BaseCleaningConfig(BaseModel):
    remove_html: bool = False
    remove_control_chars: bool = True
    manual_blacklists: List[str] = Field(default_factory=list) # List of characters/strings to remove

class FormattingConfig(BaseModel):
    fullwidth_halfwidth: str = "none" # "none", "to_halfwidth", "to_fullwidth" (refined in later phases)
    paragraph_indent: bool = False
    empty_line_threshold: int = 2
    normalize_line_breaks: bool = True

class ChapterConfig(BaseModel):
    built_in_patterns: bool = True
    custom_regex: Optional[str] = None
    renumber: bool = False

class StitchingConfig(BaseModel):
    enable: bool = False

class RuleConfig(BaseModel):
    encoding: EncodingConfig = Field(default_factory=EncodingConfig)
    base_cleaning: BaseCleaningConfig = Field(default_factory=BaseCleaningConfig)
    formatting: FormattingConfig = Field(default_factory=FormattingConfig)
    chapter: ChapterConfig = Field(default_factory=ChapterConfig)
    stitching: StitchingConfig = Field(default_factory=StitchingConfig)
