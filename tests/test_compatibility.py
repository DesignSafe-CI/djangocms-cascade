from types import SimpleNamespace
from unittest.mock import patch

from cms.api import add_plugin
from cms.models import CMSPlugin
from cms.models.placeholdermodel import Placeholder
from cms.utils.plugins import get_plugin_restrictions
from django.contrib.sites.models import Site
try:
    from cms.test_utils.util.context_managers import override_placeholder_conf
except ImportError:
    from django.test import override_settings
    def override_placeholder_conf(conf):
        return override_settings(CMS_PLACEHOLDER_CONF=conf)

from cmsplugin_cascade.bootstrap3.container import BootstrapContainerPlugin, BootstrapRowPlugin
from cmsplugin_cascade.bootstrap3.accordion import BootstrapAccordionPlugin, BootstrapAccordionPanelPlugin
from cmsplugin_cascade.bootstrap3.secondary_menu import BootstrapSecondaryMenuPlugin
from cmsplugin_cascade.compat import get_placeholder_template, get_page_queryset
from .test_base import CascadeTestCase


class CMSCompatibilityTest(CascadeTestCase):
    def test_child_classes_include_only_dynamic_children_when_requested(self):
        slot = self.placeholder.slot
        self.assertIn('BootstrapRowPlugin', BootstrapContainerPlugin.get_child_classes(
            slot, None, only_uncached=False))
        with patch.object(BootstrapRowPlugin, 'cache_parent_classes', True, create=True):
            self.assertNotIn('BootstrapRowPlugin', BootstrapContainerPlugin.get_child_classes(
                slot, None, only_uncached=True))
        with patch.object(BootstrapRowPlugin, 'cache_parent_classes', False, create=True):
            self.assertIn('BootstrapRowPlugin', BootstrapContainerPlugin.get_child_classes(
                slot, None, only_uncached=True))

    def test_transparent_wrapper_filters_direct_and_inherited_children(self):
        slot = self.placeholder.slot
        with patch.object(BootstrapAccordionPanelPlugin, 'cache_parent_classes', True):
            self.assertNotIn('BootstrapAccordionPanelPlugin', BootstrapAccordionPlugin.get_child_classes(
                slot, None, only_uncached=True))
        with patch.object(BootstrapAccordionPanelPlugin, 'cache_parent_classes', False):
            self.assertIn('BootstrapAccordionPanelPlugin', BootstrapAccordionPlugin.get_child_classes(
                slot, None, only_uncached=True))
        # Panels have no direct child list and inherit their ancestor's restrictions.
        self.assertIsInstance(BootstrapAccordionPanelPlugin.get_child_classes(
            slot, None, only_uncached=True), list)

    def test_editor_restrictions_on_initial_and_cached_lookup(self):
        instance = add_plugin(self.placeholder, BootstrapContainerPlugin, 'en')
        cache = {}
        for _ in range(2):
            children, parents = get_plugin_restrictions(
                instance, restrictions_cache=cache)
            self.assertIn('BootstrapRowPlugin', children)

    def test_sibling_navigation_is_scoped_to_parent_placeholder_and_language(self):
        first = add_plugin(self.placeholder, BootstrapContainerPlugin, 'en')
        add_plugin(self.placeholder, BootstrapRowPlugin, 'en', target=first)
        second = add_plugin(self.placeholder, BootstrapContainerPlugin, 'en')
        third = add_plugin(self.placeholder, BootstrapContainerPlugin, 'en')
        other = Placeholder.objects.create(slot='other')
        add_plugin(other, BootstrapContainerPlugin, 'en')
        add_plugin(self.placeholder, BootstrapContainerPlugin, 'de')
        plugin = second.get_plugin_class_instance()
        self.assertEqual(plugin.get_previous_instance(second).pk, first.pk)
        self.assertEqual(plugin.get_next_instance(second).pk, third.pk)
        self.assertIsNone(plugin.get_previous_instance(first))
        self.assertIsNone(plugin.get_next_instance(third))

    def test_template_specific_glossary_and_non_page_placeholder(self):
        self.assertEqual(get_placeholder_template(self.placeholder), 'testing.html')
        with override_placeholder_conf({
            'testing.html Main Content': {'glossary': {'theme': 'test-theme'}},
        }):
            instance = add_plugin(self.placeholder, BootstrapContainerPlugin, 'en')
            self.assertEqual(instance.get_parent_glossary(), {'theme': 'test-theme'})
        other = Placeholder.objects.create(slot='other')
        self.assertIsNone(get_placeholder_template(other))

    def test_page_choices_and_secondary_menu_form(self):
        self.assertIn(self.home_page, get_page_queryset(Site.objects.get_current()))
        self.home_page.reverse_id = 'home'
        self.home_page.save()
        plugin = BootstrapSecondaryMenuPlugin(BootstrapSecondaryMenuPlugin.model, self.admin_site)
        form = plugin.get_form(self.request)
        self.assertIn(('home', 'HOME'), list(form.glossary_fields[0].widget.choices))

    def test_sanitizing_existing_plugin_keeps_tree_intact(self):
        instance = add_plugin(self.placeholder, BootstrapContainerPlugin, 'en')
        plugin_class = instance.plugin_class
        def sanitize(obj):
            obj.glossary['sanitized'] = True
            return True
        with patch.object(plugin_class, 'sanitize_model', side_effect=sanitize):
            instance.save(sanitize_only=True)
        instance.refresh_from_db()
        self.assertTrue(instance.glossary['sanitized'])
        self.assertEqual(CMSPlugin.objects.filter(placeholder=self.placeholder).count(), 1)

    def test_edit_mode_uses_current_toolbar_property(self):
        instance = add_plugin(self.placeholder, BootstrapContainerPlugin, 'en')
        self.request.toolbar = SimpleNamespace(edit_mode_active=True)
        self.assertTrue(instance.get_plugin_class_instance().in_edit_mode(self.request, self.placeholder))
