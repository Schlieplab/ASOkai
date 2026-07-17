import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.abspath('../../src'))

project = 'ASOkai'
author = 'Schlieplab'
copyright = f"{datetime.now().year}, Alexander Schliep"
release = '0.1.0'
version = release

extensions = [
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.napoleon',
    'sphinx.ext.viewcode',
    'sphinx.ext.intersphinx',
    'sphinx.ext.todo',
]

autosummary_generate = True
todo_include_todos = True
autodoc_typehints = 'description'
autodoc_member_order = 'bysource'
autodoc_default_options = {
    'members': True,
    'undoc-members': False,
    'show-inheritance': True,
}

napoleon_google_docstring = True
napoleon_numpy_docstring = True

intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
}

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

html_theme = 'sphinx_rtd_theme'
html_last_updated_fmt = '%Y-%m-%d'
html_title = 'ASOkai Documentation'

html_theme_options = {
    'collapse_navigation': False,
    'navigation_depth': 4,
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
        if hasattr(obj, "__doc__"):
            obj.__doc__ = None

def setup(app):
    app.connect("autodoc-process-docstring", _strip_module_docstring)