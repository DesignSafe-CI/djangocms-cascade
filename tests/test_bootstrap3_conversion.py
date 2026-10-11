"""Run integration cases with --ds=tests.frontend_settings and frontend installed."""
from io import StringIO
from unittest.mock import patch

import pytest
from django.apps import apps
from django.core.management import call_command
from django.core.management.base import CommandError

from cmsplugin_cascade.bootstrap3.migration import TARGETS, translate


def test_grid_preserves_bootstrap3_viewport_thresholds():
    result = translate('BootstrapColumnPlugin', {
        'xs-column-width': 'col-xs-12', 'sm-column-width': 'col-sm-6',
        'md-column-width': 'col-md-4', 'lg-column-offset': 'col-lg-offset-0',
        'extra_element_id': 'main', 'extra_css_classes': ['custom'],
    })
    assert result.config == {
        'xs_col': 12, 'md_col': 6, 'lg_col': 4, 'xl_offset': 0,
        'text_alignment': '', 'attributes': {'id': 'main', 'class': 'custom'},
    }
    assert not result.warnings


def test_missing_column_width_stacks_at_mobile_sizes():
    assert translate('BootstrapColumnPlugin', {}).config['xs_col'] == 12


@pytest.mark.parametrize('value', ['col-sm-13', 'col-xs-6', 'bogus', 6])
def test_invalid_width_is_rejected(value):
    with pytest.raises(ValueError):
        translate('BootstrapColumnPlugin', {'sm-column-width': value})


def test_push_pull_and_unknown_options_are_reported():
    result = translate('BootstrapColumnPlugin', {'sm-column-ordering': 'col-sm-push-6', 'custom': 'value'})
    assert len(result.warnings) == 2
    assert 'custom' in result.warnings[1]


@pytest.mark.parametrize('link,expected', [
    ({'type': 'exturl', 'url': 'https://example.com'}, {'external_link': 'https://example.com'}),
    ({'type': 'email', 'email': 'hello@example.com'}, {'external_link': 'mailto:hello@example.com'}),
    ({'type': 'cmspage', 'model': 'cms.Page', 'pk': 3}, {'internal_link': 'cms.page:3'}),
])
def test_button_link_schema(link, expected):
    config = translate('BootstrapButtonPlugin', {'link': link, 'link_content': 'Click', 'button_type': 'btn-default'}).config
    assert config['link'] == expected
    assert config['link_context'] == 'secondary'
    assert config['name'] == 'Click'


def test_carousel_interval_uses_milliseconds():
    assert translate('CarouselPlugin', {'interval': 3}).config['carousel_interval'] == 3000


def test_accordion_open_state_uses_parent():
    result = translate('BootstrapAccordionPanelPlugin', {'panel_title': 'Title'}, {'first_is_open': True}, True)
    assert result.config['accordion_item_open'] is True
    assert translate('BootstrapAccordionPanelPlugin', {}, {'first_is_open': False}, True).config['accordion_item_open'] is False


frontend = pytest.mark.skipif(not apps.is_installed('djangocms_frontend'), reason='Requires tests.frontend_settings and djangocms-frontend')


@pytest.fixture
def source_tree():
    from cms.models import CMSPlugin, Placeholder
    from cmsplugin_cascade.models import CascadeElement
    placeholder = Placeholder.objects.create(slot='Main Content')

    def create(plugin_type, glossary=None, parent=None, language='en'):
        base = CMSPlugin.objects.create(
            placeholder=placeholder, language=language, plugin_type=plugin_type,
            parent=parent, position=CMSPlugin.objects.filter(placeholder=placeholder).count() + 1,
        )
        CascadeElement(cmsplugin_ptr_id=base.pk, glossary=glossary or {}).save_base(raw=True, force_insert=True)
        return base

    return placeholder, create


def convert(**kwargs):
    out = StringIO()
    call_command('convert_bootstrap3', stdout=out, **kwargs)
    return out.getvalue()


@frontend
@pytest.mark.django_db
def test_dry_run_and_apply_preserve_grid_tree(source_tree):
    from cms.models import CMSPlugin
    from djangocms_frontend.models import FrontendUIItem
    from cmsplugin_cascade.models import CascadeElement
    _, create = source_tree
    container = create('BootstrapContainerPlugin', {'fluid': True})
    row = create('BootstrapRowPlugin', parent=container)
    col = create('BootstrapColumnPlugin', {'sm-column-width': 'col-sm-6'}, row)
    before = list(CMSPlugin.objects.values())
    assert '3 convertible' in convert()
    assert list(CMSPlugin.objects.values()) == before
    assert not FrontendUIItem.objects.exists()
    assert 'Converted 3' in convert(apply=True)
    after = list(CMSPlugin.objects.values())
    for old, new in zip(before, after):
        assert {k: v for k, v in old.items() if k != 'plugin_type'} == {k: v for k, v in new.items() if k != 'plugin_type'}
    assert FrontendUIItem.objects.get(pk=col.pk).config['md_col'] == 6
    assert CascadeElement.objects.count() == 3
    assert CMSPlugin.objects.get(pk=col.pk).get_plugin_instance()[0].__class__.__name__ == 'GridColumn'
    assert 'Converted 0' in convert(apply=True)


@frontend
@pytest.mark.django_db
def test_all_direct_equivalents_and_same_name_carousels_are_idempotent(source_tree):
    from cms.models import CMSPlugin
    from djangocms_frontend.models import FrontendUIItem
    _, create = source_tree
    source = [create(name) for name in TARGETS]
    convert(apply=True, allow_lossy=True, include_text_links=True)
    for plugin in source:
        assert CMSPlugin.objects.get(pk=plugin.pk).plugin_type == TARGETS[plugin.plugin_type]
        assert FrontendUIItem.objects.get(pk=plugin.pk).config['_cascade_migration']['source_id'] == plugin.pk
    assert 'Converted 0' in convert(apply=True)


@frontend
@pytest.mark.django_db
def test_lossy_apply_requires_explicit_flag(source_tree):
    from djangocms_frontend.models import FrontendUIItem
    _, create = source_tree
    create('BootstrapColumnPlugin', {'sm-column-ordering': 'col-sm-push-6'})
    with pytest.raises(CommandError, match='--allow-lossy'):
        convert(apply=True)
    assert not FrontendUIItem.objects.exists()


@frontend
@pytest.mark.django_db
def test_invalid_late_plugin_prevents_any_conversion(source_tree):
    from cms.models import CMSPlugin
    from djangocms_frontend.models import FrontendUIItem
    _, create = source_tree
    first = create('BootstrapContainerPlugin')
    create('BootstrapColumnPlugin', {'sm-column-width': 'invalid'})
    with pytest.raises(CommandError):
        convert(apply=True)
    assert not FrontendUIItem.objects.exists()
    assert CMSPlugin.objects.get(pk=first.pk).plugin_type == 'BootstrapContainerPlugin'


@frontend
@pytest.mark.django_db
def test_panel_expands_header_body_footer_and_preserves_children(source_tree):
    from cms.models import CMSPlugin
    from djangocms_frontend.models import FrontendUIItem
    _, create = source_tree
    panel = create('BootstrapPanelPlugin', {'heading': 'Hello', 'footer': 'Goodbye', 'heading_size': 'h3'})
    row = create('BootstrapRowPlugin', parent=panel)
    convert(apply=True)
    children = list(CMSPlugin.objects.filter(parent_id=panel.pk).order_by('position'))
    assert [FrontendUIItem.objects.get(pk=child.pk).config['inner_type'] for child in children] == ['card-header', 'card-body', 'card-footer']
    assert CMSPlugin.objects.get(pk=row.pk).parent_id == children[1].pk
    from djangocms_text_ckeditor.models import Text
    assert list(Text.objects.order_by('position').values_list('body', flat=True)) == ['<h3>Hello</h3>', 'Goodbye']


@frontend
@pytest.mark.django_db
def test_expansion_failure_rolls_back_base_and_frontend_rows(source_tree):
    from cms.models import CMSPlugin
    from djangocms_frontend.models import FrontendUIItem
    _, create = source_tree
    panel = create('BootstrapPanelPlugin')
    with patch('cmsplugin_cascade.management.commands.convert_bootstrap3.Command.expand_panel', side_effect=RuntimeError('failure')):
        with pytest.raises(RuntimeError):
            convert(apply=True)
    assert CMSPlugin.objects.get(pk=panel.pk).plugin_type == 'BootstrapPanelPlugin'
    assert not FrontendUIItem.objects.exists()


@frontend
@pytest.mark.django_db
def test_filtering_and_unsupported_plugins(source_tree):
    from cms.models import CMSPlugin
    from djangocms_frontend.models import FrontendUIItem
    placeholder, create = source_tree
    create('BootstrapContainerPlugin', language='en')
    french = create('BootstrapContainerPlugin', language='fr')
    unsupported = create('BootstrapSecondaryMenuPlugin')
    with pytest.raises(CommandError, match='--skip-unsupported'):
        convert(apply=True)
    convert(apply=True, language=['en'], placeholder=[placeholder.pk], skip_unsupported=True)
    assert FrontendUIItem.objects.count() == 1
    assert CMSPlugin.objects.get(pk=french.pk).plugin_type == 'BootstrapContainerPlugin'
    assert CMSPlugin.objects.get(pk=unsupported.pk).plugin_type == 'BootstrapSecondaryMenuPlugin'


@frontend
@pytest.mark.django_db
def test_shared_glossary_is_materialized(source_tree):
    from cmsplugin_cascade.models import CascadeElement, SharedGlossary
    from djangocms_frontend.models import FrontendUIItem
    _, create = source_tree
    plugin = create('BootstrapColumnPlugin', {'sm-column-width': 'col-sm-3'})
    shared = SharedGlossary(plugin_type='BootstrapColumnPlugin', identifier='shared', glossary={'sm-column-width': 'col-sm-6'})
    shared.save_base(raw=True, force_insert=True)
    CascadeElement.objects.filter(pk=plugin.pk).update(shared_glossary=shared)
    convert(apply=True)
    assert FrontendUIItem.objects.get(pk=plugin.pk).config['md_col'] == 6


@frontend
@pytest.mark.django_db
def test_button_resolves_real_frontend_link(source_tree):
    from cms.models import CMSPlugin
    _, create = source_tree
    button = create('BootstrapButtonPlugin', {'link': {'type': 'exturl', 'url': 'https://example.com'}, 'link_content': 'Visit'})
    convert(apply=True)
    instance = CMSPlugin.objects.get(pk=button.pk).get_plugin_instance()[0]
    assert instance.get_link() == 'https://example.com'
    assert instance.config['link_type'] == 'btn'


@frontend
@pytest.mark.django_db
def test_gallery_expands_ordered_image_columns_and_preserves_inline_data(source_tree):
    from cms.models import CMSPlugin
    from cmsplugin_cascade.models import CascadeElement, SortableInlineCascadeElement
    from djangocms_frontend.models import FrontendUIItem
    from filer.models import Image
    _, create = source_tree
    gallery = create('BootstrapGalleryPlugin')
    image = Image.objects.create(original_filename='example.png', file='migration/example.png')
    element = CascadeElement.objects.get(pk=gallery.pk)
    for order, title in [(2, 'Second'), (1, 'First')]:
        SortableInlineCascadeElement.objects.create(cascade_element=element, order=order, glossary={
            'image': {'model': 'filer.Image', 'pk': image.pk}, 'image_title': title,
        })
    convert(apply=True, allow_lossy=True)
    columns = CMSPlugin.objects.filter(parent_id=gallery.pk).order_by('position')
    images = [FrontendUIItem.objects.get(pk=CMSPlugin.objects.get(parent_id=col.pk).pk) for col in columns]
    assert [item.config['attributes']['title'] for item in images] == ['First', 'Second']
    assert all(item.config['picture']['pk'] == image.pk for item in images)
    assert SortableInlineCascadeElement.objects.count() == 2
    assert 'Converted 0' in convert(apply=True)


@frontend
@pytest.mark.django_db
def test_missing_gallery_image_is_reported_in_dry_run(source_tree):
    from cmsplugin_cascade.models import CascadeElement, SortableInlineCascadeElement
    _, create = source_tree
    gallery = create('BootstrapGalleryPlugin')
    SortableInlineCascadeElement.objects.create(cascade_element=CascadeElement.objects.get(pk=gallery.pk), order=0, glossary={
        'image': {'model': 'filer.Image', 'pk': 9999},
    })
    with pytest.raises(CommandError):
        convert()


@frontend
@pytest.mark.django_db
def test_text_link_filter_migrates_standard_links_without_other_plugin_errors(source_tree):
    from cms.models import CMSPlugin
    from djangocms_frontend.models import FrontendUIItem
    _, create = source_tree
    link = create('TextLinkPlugin', {
        'link_content': '3-Story Reconfigurable Modular Testbed Building',
        'link': {'url': 'http://chei.ucsd.edu/MTB2/index.html', 'type': 'exturl'},
        'target': '_blank', 'render_template': 'cascade/link/text-link.html',
        'title': '3-Story Reconfigurable Modular Testbed Building',
    })
    orphan = create('BootstrapColumnPlugin')
    from cmsplugin_cascade.models import CascadeElement
    # Remove just the child row to simulate a broken unrelated plugin.
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute('DELETE FROM cmsplugin_cascade_element WHERE cmsplugin_ptr_id = %s', [orphan.pk])
    report = convert(plugin_type=['TextLinkPlugin'])
    assert '1 convertible' in report
    assert 'REVIEW:' not in report
    assert not FrontendUIItem.objects.exists()
    convert(plugin_type=['TextLinkPlugin'], apply=True)
    item = CMSPlugin.objects.get(pk=link.pk).get_plugin_instance()[0]
    assert item.get_link() == 'http://chei.ucsd.edu/MTB2/index.html'
    assert item.config['name'] == '3-Story Reconfigurable Modular Testbed Building'
    assert item.config['target'] == '_blank'
    assert item.config['attributes']['title'] == '3-Story Reconfigurable Modular Testbed Building'
    assert CMSPlugin.objects.filter(pk=orphan.pk).exists()
    assert 'Converted 0' in convert(plugin_type=['TextLinkPlugin'], apply=True)
