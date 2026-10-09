"""Compatibility helpers shared by django CMS 3 and 4+ integrations."""
from cms import __version__ as cms_version
from django.apps import apps
from packaging.version import Version


CMS4 = Version(cms_version) >= Version('4.0')


def is_installed(app_name):
    return apps.is_installed(app_name)


def get_placeholder_template(placeholder):
    # CMS 4 attaches placeholders to PageContent, where the template now lives.
    if CMS4:
        source = getattr(placeholder, 'source', None)
        get_template = getattr(source, 'get_template', None)
        return get_template() if callable(get_template) else None
    page = getattr(placeholder, 'page', None)
    return page.template if page else None


def get_page_queryset(site):
    from cms.models import Page

    pages = Page.objects.on_site(site)
    return pages if CMS4 else pages.drafts()


def clear_placeholder(placeholder):
    if hasattr(placeholder, 'clear'):
        placeholder.clear()
    else:
        placeholder.get_plugins().delete()
