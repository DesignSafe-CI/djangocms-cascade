import io
import json
import os
from distutils.version import LooseVersion
from cms import __version__ as CMS_VERSION
from cms.toolbar.utils import get_toolbar_from_request
from django import template
from django.conf import settings
from django.core.cache import caches
from django.template.exceptions import TemplateDoesNotExist
from django.contrib.staticfiles import finders
from django.utils.safestring import mark_safe
from classytags.arguments import Argument
from classytags.core import Options, Tag

register = template.Library()


class StrideRenderer(Tag):
    """
    Render the serialized content of a placeholder field using the full cascade of plugins.
    {% render_cascade "cascade-data.json" %}

    Keyword arguments:
    datafile -- Filename containing the cascade tree. Must be file locatable by Django's
    static file finders.
    """
    name = 'render_cascade'
    options = Options(
        Argument('datafile'),
    )

    def render_tag(self, context, datafile):
        from sekizai.helpers import get_varname as get_sekizai_context_key
        from cmsplugin_cascade.strides import StrideContentRenderer

        content_renderer = StrideContentRenderer(context['request'])
        tree_data_key = 'cascade-strides:' + datafile
        sekizai_context_key = get_sekizai_context_key()

        cache = caches['default']
        tree_data = cache.get(tree_data_key) if cache else None
        if tree_data is None:
            jsonfile = finders.find(datafile)
            if not jsonfile:
                raise IOError("Unable to find file: {}".format(datafile))
            with io.open(jsonfile) as fp:
                tree_data = json.load(fp)
            if cache:
                cache.set(tree_data_key, tree_data)

        with context.push(cms_content_renderer=content_renderer):
            content = content_renderer.render_cascade(context, tree_data)

        # some templates use Sekizai's templatetag `addtoblock` or `add_data`, which have to be re-added to the context
        cache = caches['default']
        if cache:
            SEKIZAI_CONTENT_HOLDER = cache.get_or_set(sekizai_context_key, context.get(sekizai_context_key))
            if SEKIZAI_CONTENT_HOLDER:
                for name in SEKIZAI_CONTENT_HOLDER:
                    context[sekizai_context_key].setdefault(name, SEKIZAI_CONTENT_HOLDER[name])
        return content

register.tag('render_cascade', StrideRenderer)


class RenderPlugin(Tag):
    name = 'render_plugin'
    options = Options(
        Argument('plugin')
    )

    def render_tag(self, context, plugin):
        if not plugin:
            return ''

        toolbar = get_toolbar_from_request(context['request'])
        content_renderer = context.get('cms_content_renderer', toolbar.content_renderer)
        content = content_renderer.render_plugin(
            instance=plugin,
            context=context,
            editable=toolbar.edit_mode_active,
        )
        return content

register.tag('render_plugin', RenderPlugin)


@register.simple_tag
def sphinx_docs_include(path):
    filename = os.path.join(settings.SPHINX_DOCS_ROOT, path)
    if not os.path.exists(filename):
        raise TemplateDoesNotExist("'{path}' does not exist".format(path=path))
    with io.open(filename) as fh:
        return mark_safe(fh.read())
