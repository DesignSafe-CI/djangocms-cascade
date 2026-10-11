"""Optional integration test settings: install djangocms-frontend separately."""
from .settings import *  # noqa: F403

# The old carousel has the same plugin names as the target; use stored rows directly.
CMSPLUGIN_CASCADE_PLUGINS = ()
INSTALLED_APPS = INSTALLED_APPS + [  # noqa: F405
    'djangocms_link',
    'djangocms_frontend',
    'djangocms_frontend.contrib.grid',
    'djangocms_frontend.contrib.link',
    'djangocms_frontend.contrib.image',
    'djangocms_frontend.contrib.accordion',
    'djangocms_frontend.contrib.tabs',
    'djangocms_frontend.contrib.carousel',
    'djangocms_frontend.contrib.card',
    'djangocms_frontend.contrib.jumbotron',
]
