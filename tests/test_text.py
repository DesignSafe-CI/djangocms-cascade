from unittest.mock import patch

from django.apps import apps
from django.contrib import admin
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from cms.toolbar.toolbar import CMSToolbar
from djangocms_text.models import Text
from djangocms_text.utils import plugin_tags_to_id_list

from cmsplugin_cascade.clipboard.admin import CascadeClipboardAdmin
from cmsplugin_cascade.models import CascadeClipboard
from .test_base import CascadeTestCase


class TextClipboardTest(CascadeTestCase):
    def test_restore_and_serialize_embedded_link(self):
        data = {'plugins': [['TextPlugin', {
            'body': '<p>Visit <cms-plugin id="1001"></cms-plugin>.</p>',
            'pk': 1000,
        }, [['TextLinkPlugin', {
            'pk': 1001,
            'glossary': {
                'link': {'type': 'exturl', 'url': 'https://example.com/'},
                'link_content': 'Example',
            },
        }, []]]]]}
        request = self.get_request('/')
        request.toolbar = CMSToolbar(request)
        clipboard_admin = CascadeClipboardAdmin(CascadeClipboard, admin.site)
        clipboard_admin._deserialize_to_clipboard(request, data)

        reference = request.toolbar.clipboard.get_plugins().first().get_plugin_instance()[0]
        text = Text.objects.get(placeholder=reference.placeholder_ref)
        child = text.get_children().get()
        self.assertNotEqual(child.pk, 1001)
        self.assertEqual(plugin_tags_to_id_list(text.body), [child.pk])
        html = self.get_html(text, self.get_request_context())
        self.assertIn('https://example.com/', html)
        self.assertIn('Example', html)

        serialized = clipboard_admin._serialize_from_clipboard('en')
        plugin_type, text_data, children = serialized['plugins'][0]
        self.assertEqual(plugin_type, 'TextPlugin')
        self.assertEqual(text_data['body'], text.body)
        self.assertEqual(children[0][0], 'TextLinkPlugin')


class TextEditorConfigurationTest(SimpleTestCase):
    @override_settings(TEXT_EDITOR='tiptap')
    def test_default_editor_does_not_require_ckeditor_icon_settings(self):
        with patch('cmsplugin_cascade.apps.TEXT_EDITOR_SETTINGS', {}):
            apps.get_app_config('cmsplugin_cascade').ready()

    @override_settings(TEXT_EDITOR='djangocms_text.contrib.text_ckeditor4.ckeditor4')
    def test_ckeditor_icon_configuration_error_uses_new_setting_name(self):
        with patch('cmsplugin_cascade.apps.TEXT_EDITOR_SETTINGS', {}):
            with self.assertRaisesMessage(ImproperlyConfigured, 'TEXT_EDITOR_SETTINGS'):
                apps.get_app_config('cmsplugin_cascade').ready()
