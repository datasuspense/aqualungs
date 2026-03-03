from datetime import datetime
import re

from pydantic import BaseModel, Field, HttpUrl, field_validator


class Article(BaseModel):
    arxiv_id: str = Field(..., min_length=6, max_length=32)
    title: str = Field(..., max_length=2048)
    authors: list[str]
    created_at: str
    annotation: str
    subjects: list[str]
    url: HttpUrl
    github_urls: list[HttpUrl] = Field(default_factory=list)
    other_urls: list[HttpUrl] = Field(default_factory=list)
    is_updated: int = 0

    @field_validator('title', 'annotation')
    @classmethod
    def normalize_str(cls, value: str) -> str:
        return value.strip()

    @field_validator('arxiv_id')
    @classmethod
    def validate_arxiv_id(cls, value: str) -> str:
        v = value.strip()
        pattern = re.compile(
            r"^(?:\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)$",
            re.IGNORECASE)
        if not pattern.match(v):
            raise ValueError("Invalid arXiv ID format")
        return v

    @field_validator('url')
    @classmethod
    def validate_url(cls, value: HttpUrl) -> HttpUrl:
        if value.host not in {'arxiv.org', 'www.arxiv.org'}:
            raise ValueError("URL must be on arxiv.org")
        return value

    @field_validator('created_at')
    @classmethod
    def validate_created_at(cls, value: str) -> str:
        v = value.strip()
        try:
            datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
        except ValueError as e:
            raise ValueError("created_at must be in YYYY-mm-dd format") from e
        return v

    @field_validator('github_urls')
    @classmethod
    def validate_github_urls(cls, value: list[HttpUrl]) -> list[HttpUrl]:
        for item in value:
            if item.host not in {'github.com', 'www.github.com'}:
                raise ValueError("URL must be on github.com")
        return value
