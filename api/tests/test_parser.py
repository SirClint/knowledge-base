import pytest
from docs_.parser import parse_doc, ParsedDoc
from pathlib import Path
import tempfile, os

SAMPLE_DOC = """\
---
title: Kubernetes Deploy
tags: [kubernetes, deployment]
created: 2024-01-15
last_reviewed: 2024-01-15
review_interval: 30d
owner: alice
status: current
---

# Kubernetes Deploy

Steps to deploy to production.
"""


def test_parse_frontmatter():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(SAMPLE_DOC)
        path = f.name
    try:
        doc = parse_doc(Path(path))
        assert doc.title == "Kubernetes Deploy"
        assert "kubernetes" in doc.tags
        assert doc.owner == "alice"
        assert doc.status == "current"
        assert doc.review_interval == "30d"
    finally:
        os.unlink(path)


def test_parse_body():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(SAMPLE_DOC)
        path = f.name
    try:
        doc = parse_doc(Path(path))
        assert "Steps to deploy" in doc.body
    finally:
        os.unlink(path)


def test_parse_missing_frontmatter():
    content = "# Just a title\n\nSome content."
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write(content)
        path = f.name
    try:
        doc = parse_doc(Path(path))
        assert doc.title == ""
        assert doc.tags == []
    finally:
        os.unlink(path)
