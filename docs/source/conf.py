import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.abspath('../../src'))
sys.path.insert(0, str(Path(__file__).parent / '_extensions'))

project = 'ASOkai'
author = 'Schlieplab'
copyright = f"{datetime.now().year}, Alexander Schliep"
release = '0.1.0'
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
        if hasattr(obj, "__doc__"):
            obj.__doc__ = None


def setup(app):
    app.connect("autodoc-process-docstring", _strip_module_docstring)
