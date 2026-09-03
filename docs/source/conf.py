#!/usr/bin/env python
"""
Filename: docs/source/conf.py
Author: Arash Ayat
Copyright: 2026, Alexander Schliep
Description: Sphinx configuration for the ASOkai documentation.
License: LGPL-3.0-or-later
"""

import sys
from datetime import datetime
from importlib.metadata import version as distribution_version
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent / "_extensions"))

project = 'ASOkai'
author = 'Schlieplab'
copyright = f"{datetime.now().year}, Alexander Schliep"
release = distribution_version("ASOkai")
version = release

extensions = [
    'contract_docs',
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
]

autosummary_generate = True

autodoc_typehints = 'description'
autodoc_member_order = 'bysource'
autodoc_default_options = {
    'members': True,
    'undoc-members': False,
    'show-inheritance': True,
}

napoleon_google_docstring = True
napoleon_numpy_docstring = True

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']
html_static_path = ['_static']
html_css_files = ['asokai.css']

html_theme = 'sphinx_rtd_theme'
html_last_updated_fmt = '%Y-%m-%d'
html_title = 'ASOkai Documentation'

html_theme_options = {
    'collapse_navigation': False,
    'navigation_depth': 3,
    'includehidden': True,
    'titles_only': False,
}

html_context = {
    'display_github': True,
    'github_user': 'Schlieplab',
    'github_repo': 'ASOkai',
    'github_version': 'master',
    'conf_py_path': '/docs/source/',
}


def _strip_module_docstring(app, what, name, obj, options, lines):
    if what == "module":
        lines[:] = []


def setup(app):
    app.connect("autodoc-process-docstring", _strip_module_docstring)
