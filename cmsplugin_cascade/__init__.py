# -*- coding: utf-8 -*-
from __future__ import unicode_literals
"""
See PEP 386 (https://www.python.org/dev/peps/pep-0386/)

Release logic:
 1. Remove ".devX" from __version__ (below) and project.version in pyproject.toml
 2. Remove ".devX" latest version in docs/source/changelog.rst and run uv lock
 3. git add pyproject.toml uv.lock cmsplugin_cascade/__init__.py docs/source/changelog.rst
 4. git commit -m 'Bump to <version>'
 5. git tag <version>
 6. git push
 7. assure that all tests pass on https://travis-ci.org/jrief/djangocms-cascade
 8. git push --tags
 9. Confirm the release version and lockfile are committed
10. uv build --clear
11. uv publish
12. bump the version, append ".dev0" to __version__ and project.version
13. Run uv lock and add a new heading to docs/source/changelog.rst, named "<next-version>.dev0"
14. git add pyproject.toml uv.lock cmsplugin_cascade/__init__.py docs/source/changelog.rst
15. git commit -m 'Start with <version>'
16. git push
"""
__version__ = "0.16.3"

default_app_config = 'cmsplugin_cascade.apps.CascadeConfig'
