#!/usr/bin/env python3
"""
Build static HTML files from Jinja2 templates into docs/ directory for GitHub Pages.
"""

import os
from jinja2 import Environment, FileSystemLoader

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(REPO_ROOT, "templates")
DOCS_DIR = os.path.join(REPO_ROOT, "docs")


def build_templates():
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=False,  # Allow raw HTML partials and blocks
        trim_blocks=True,
        lstrip_blocks=True,
    )

    pages = [
        {
            "template": "index.html",
            "output": "index.html",
            "context": {
                "active_page": "index",
                "subtitle": "חיפוש והשוואת הטבות מועדוני אשראי",
                "deals_label": "הטבות פעילות",
                "stores_label": "עסקים ורשתות",
                "show_status": False,
            },
        },
        {
            "template": "nearme.html",
            "output": "nearme.html",
            "context": {
                "active_page": "nearme",
                "subtitle": "חיפוש עסקים והטבות קרובים",
                "deals_label": "הטבות באיזור",
                "stores_label": "עסקים באיזור",
                "show_status": True,
            },
        },
    ]

    for page in pages:
        tmpl = env.get_template(page["template"])
        rendered = tmpl.render(**page["context"])
        out_path = os.path.join(DOCS_DIR, page["output"])
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(rendered)
        print(f"Rendered {page['template']} -> {out_path}")


if __name__ == "__main__":
    build_templates()
