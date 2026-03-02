from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import frontmatter


@dataclass
class ParsedDoc:
    path: Path
    title: str = ""
    tags: list[str] = field(default_factory=list)
    created: Optional[str] = None
    last_reviewed: Optional[str] = None
    review_interval: str = "90d"
    owner: str = ""
    status: str = "current"
    body: str = ""


def parse_doc(path: Path) -> ParsedDoc:
    post = frontmatter.load(str(path))
    meta = post.metadata
    return ParsedDoc(
        path=path,
        title=meta.get("title", ""),
        tags=meta.get("tags", []),
        created=str(meta["created"]) if "created" in meta else None,
        last_reviewed=str(meta["last_reviewed"]) if "last_reviewed" in meta else None,
        review_interval=meta.get("review_interval", "90d"),
        owner=meta.get("owner", ""),
        status=meta.get("status", "current"),
        body=post.content,
    )
