"""Convert Cascade plugins in place, leaving their CMSPlugin/tree rows intact."""

from copy import deepcopy
from html import unescape
import json

from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import FieldDoesNotExist
from django.db import transaction

from cmsplugin_cascade.bootstrap3.migration import TARGETS, UNSUPPORTED, translate


class Command(BaseCommand):
    help = "Convert Cascade Bootstrap 3 plugins to djangocms-frontend (dry run unless --apply)."
    requires_system_checks = []

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--apply", action="store_true", help="Commit the conversion.")
        mode.add_argument("--dry-run", action="store_true", help="Report only (the default).")
        parser.add_argument("--include-text-links", action="store_true", help="Also convert Cascade TextLinkPlugin rows to avoid frontend name collisions.")
        parser.add_argument("--allow-lossy", action="store_true", help="Accept reported rendering differences.")
        parser.add_argument("--skip-unsupported", action="store_true", help="Leave plugins without equivalents unchanged.")
        parser.add_argument("--plugin-type", choices=sorted({*TARGETS, *UNSUPPORTED}), action="append", help="Convert only these source plugin types (repeatable).")
        parser.add_argument("--placeholder", type=int, action="append", help="Limit to these placeholder IDs (repeatable).")
        parser.add_argument("--language", action="append", help="Limit to these languages (repeatable).")

    def handle(self, *args, **options):
        try:
            from djangocms_frontend.models import FrontendUIItem
        except (ImportError, RuntimeError) as exc:
            raise CommandError("Install djangocms-frontend, add its base and contrib apps to INSTALLED_APPS, and migrate.") from exc
        from cms.models import CMSPlugin
        from cmsplugin_cascade.models import CascadeElement

        # Lock base rows before reading glossaries; do not change the CMSPlugin IDs or tree columns.
        with transaction.atomic():
            source_types = [name for name in TARGETS if name != "TextLinkPlugin" or options["include_text_links"]]
            selected_types = options["plugin_type"] or [*source_types, *UNSUPPORTED]
            base = CMSPlugin.objects.filter(plugin_type__in=selected_types)
            if options["placeholder"]:
                base = base.filter(placeholder_id__in=options["placeholder"])
            if options["language"]:
                base = base.filter(language__in=options["language"])
            if options["apply"]:
                base = base.select_for_update()
            plugins = list(base.order_by("pk"))
            ids = [plugin.pk for plugin in plugins]
            elements_qs = CascadeElement.objects.filter(pk__in=ids)
            if options["apply"]:
                elements_qs = elements_qs.select_for_update()
            # Avoid FOR UPDATE on the nullable shared_glossary outer join on PostgreSQL.
            if not options["apply"]:
                elements_qs = elements_qs.select_related("shared_glossary")
            elements = {element.pk: element for element in elements_qs}
            existing = {item.pk: item for item in FrontendUIItem.objects.filter(pk__in=ids)}
            plans, unsupported, errors = [], [], []
            targets = {}
            for plugin in plugins:
                element = elements.get(plugin.pk)
                item = existing.get(plugin.pk)
                if item and item.config.get("_cascade_migration", {}).get("source_id") == plugin.pk:
                    continue  # Includes same-name CarouselPlugin/CarouselSlidePlugin on repeat runs.
                if not element:
                    if item:
                        continue  # Native frontend carousel sharing the source plugin name.
                    errors.append(f"{plugin.pk}: missing CascadeElement row")
                    continue
                if plugin.plugin_type in UNSUPPORTED:
                    unsupported.append(f"{plugin.pk}: {plugin.plugin_type}: {UNSUPPORTED[plugin.plugin_type]}")
                    continue
                if item:
                    errors.append(f"{plugin.pk}: frontend row already exists without a migration marker")
                    continue
                glossary = deepcopy(element.glossary or {})
                if element.shared_glossary_id:
                    glossary.update(deepcopy(element.shared_glossary.glossary or {}))
                parent = CascadeElement.objects.filter(pk=plugin.parent_id).select_related("shared_glossary").first()
                parent_glossary = deepcopy(parent.glossary or {}) if parent else {}
                if parent and parent.shared_glossary_id:
                    parent_glossary.update(deepcopy(parent.shared_glossary.glossary or {}))
                first_id = CMSPlugin.objects.filter(parent_id=plugin.parent_id).order_by("position", "pk").values_list("pk", flat=True).first()
                try:
                    result = translate(plugin.plugin_type, glossary, parent_glossary, first_id == plugin.pk)
                    target = self.get_target(result.target, FrontendUIItem)
                    targets[result.target] = target
                    instance = target.model()
                    instance.initialize_from_form(target.form)
                    config = deepcopy(instance.config)
                    config.update(result.config)
                    config["_cascade_migration"] = {
                        "source_id": plugin.pk,
                        "source_type": plugin.plugin_type,
                        "glossary": deepcopy(element.glossary),
                        "shared_glossary_id": element.shared_glossary_id,
                        "effective_glossary": glossary,
                    }
                    if plugin.plugin_type == "BootstrapPanelPlugin":
                        self.get_target("CardInnerPlugin", FrontendUIItem)
                        if glossary.get("heading") or glossary.get("footer"):
                            self.get_text_plugin()
                    if plugin.plugin_type == "BootstrapGalleryPlugin":
                        targets["ImagePlugin"] = self.get_target("ImagePlugin", FrontendUIItem)
                        self.get_target("GridColumnPlugin", FrontendUIItem)
                        for inline in element.sortinline_elements.order_by("order", "pk"):
                            inline_config = translate("BootstrapImagePlugin", inline.glossary).config
                            self.validate_references(inline_config)
                    self.validate_references(config)
                    if config.get("background_image"):
                        from django.apps import apps
                        ref = config["background_image"]
                        image = apps.get_model(ref["model"]).objects.get(pk=ref["pk"])
                        config["attributes"]["style"] = config["attributes"].get("style", "") + f" background-image: url({json.dumps(image.url)});"
                except (CommandError, ValueError, TypeError) as exc:
                    errors.append(f"{plugin.pk}: {exc}")
                    continue
                plans.append((plugin, instance, config, glossary, result.warnings))
                self.stdout.write(f"{plugin.pk}: {plugin.plugin_type} -> {result.target}")
                if options["verbosity"] >= 2:
                    self.stdout.write(json.dumps(config, default=str, sort_keys=True))
                for warning in result.warnings:
                    self.stdout.write(f"  REVIEW: {warning}")
            for message in unsupported:
                self.stdout.write(f"UNSUPPORTED: {message}")
            for message in errors:
                self.stderr.write(f"ERROR: {message}")
            self.stdout.write(f"{len(plans)} convertible; {len(unsupported)} unsupported; {len(errors)} errors.")
            if not options["apply"]:
                self.stdout.write("Dry run: no database changes. Use --apply to convert after reviewing the report.")
                if errors:
                    raise CommandError("Resolve the reported errors before applying the conversion.")
                return
            if errors:
                raise CommandError("Conversion aborted: resolve all errors; no changes committed.")
            if unsupported and not options["skip_unsupported"]:
                raise CommandError("Conversion aborted: unsupported plugins found. Use --skip-unsupported to leave them unchanged.")
            if any(warnings for _, _, _, _, warnings in plans) and not options["allow_lossy"]:
                raise CommandError("Conversion aborted: review warnings, then use --allow-lossy to accept rendering differences.")

            for plugin, instance, config, glossary, warnings in plans:
                instance.cmsplugin_ptr_id = plugin.pk
                instance.ui_item = instance.__class__.__name__
                instance.config = config
                # raw=True skips multi-table parent saves (which would reset tree fields).
                # save_base does not invoke FrontendUIItem.save or Cascade sanitizers.
                instance.save_base(raw=True, force_insert=True)
                CMSPlugin.objects.filter(pk=plugin.pk).update(plugin_type=TARGETS[plugin.plugin_type])
            # Expand components only after every original plugin has its new model.
            for plugin, instance, config, glossary, warnings in plans:
                if plugin.plugin_type == "BootstrapPanelPlugin":
                    self.expand_panel(plugin.pk, glossary)
                elif plugin.plugin_type == "BootstrapGalleryPlugin":
                    self.expand_gallery(plugin.pk, elements[plugin.pk], targets["ImagePlugin"])
            affected = {(p.placeholder_id, p.language) for p, *_ in plans if p.placeholder_id}
            transaction.on_commit(lambda: self.clear_caches(affected))
        self.stdout.write(self.style.SUCCESS(f"Converted {len(plans)} plugins. Original Cascade rows and glossaries retained."))

    @staticmethod
    def get_target(name, concrete):
        from cms.plugin_pool import plugin_pool
        try:
            plugin = plugin_pool.get_plugin(name)
        except KeyError as exc:
            raise CommandError(f"Enable the frontend contrib app registering {name} and run migrate.") from exc
        if plugin.model._meta.concrete_model is not concrete:
            raise CommandError(f"{name} is not a frontend plugin. Disable the matching Cascade module in CMSPLUGIN_CASCADE_PLUGINS.")
        return plugin

    @staticmethod
    def get_text_plugin():
        from cms.plugin_pool import plugin_pool
        try:
            plugin = plugin_pool.get_plugin("TextPlugin")
            plugin.model._meta.get_field("body")
            return plugin
        except (KeyError, LookupError, FieldDoesNotExist) as exc:
            raise CommandError("Panel headings/footers require a TextPlugin with a body field.") from exc

    @staticmethod
    def validate_references(config):
        from django.apps import apps
        for key in ("picture", "carousel_image", "background_image"):
            reference = config.get(key)
            if reference:
                try:
                    model = apps.get_model(reference["model"])
                    exists = model.objects.filter(pk=reference["pk"]).exists()
                except (LookupError, KeyError, TypeError, ValueError) as exc:
                    raise CommandError(f"Invalid {key} reference: {reference!r}") from exc
                if not exists:
                    raise CommandError(f"Missing {key} object: {reference!r}")

    @staticmethod
    def add_frontend(parent, name, config):
        from cms.api import add_plugin
        from cms.plugin_pool import plugin_pool
        plugin = plugin_pool.get_plugin(name)
        instance = plugin.model().initialize_from_form(plugin.form)
        defaults = deepcopy(instance.config)
        defaults.update(config)
        return add_plugin(parent.placeholder, name, parent.language, target=parent,
                          config=defaults, tag_type="div")

    def expand_panel(self, pk, glossary):
        from cms.api import add_plugin
        from cms.models import CMSPlugin
        panel = CMSPlugin.objects.get(pk=pk)
        children = list(panel.get_children())
        if glossary.get("heading"):
            header = self.add_frontend(panel, "CardInnerPlugin", {"inner_type": "card-header"})
            heading = unescape(glossary["heading"])
            size = glossary.get("heading_size", "")
            if size in ("h1", "h2", "h3", "h4", "h5", "h6"):
                heading = f"<{size}>{heading}</{size}>"
            add_plugin(panel.placeholder, "TextPlugin", panel.language, target=header, body=heading)
        body = self.add_frontend(panel, "CardInnerPlugin", {"inner_type": "card-body"})
        for child in children:
            child.refresh_from_db()
            body.refresh_from_db()
            if hasattr(child, "path"):  # CMS 3/treebeard.
                child.move(body, "last-child")
                CMSPlugin.objects.filter(pk=child.pk).update(parent_id=body.pk)
            else:
                position = panel.placeholder.get_next_plugin_position(panel.language, parent=body, insert_order="last")
                panel.placeholder.move_plugin(child, position, target_plugin=body)
        if glossary.get("footer"):
            panel.refresh_from_db()
            footer = self.add_frontend(panel, "CardInnerPlugin", {"inner_type": "card-footer"})
            add_plugin(panel.placeholder, "TextPlugin", panel.language, target=footer, body=unescape(glossary["footer"]))

    def expand_gallery(self, pk, element, image_plugin):
        from cms.models import CMSPlugin
        gallery = CMSPlugin.objects.get(pk=pk)
        for inline in element.sortinline_elements.order_by("order", "pk"):
            result = translate("BootstrapImagePlugin", inline.glossary)
            self.validate_references(result.config)
            column = self.add_frontend(gallery, "GridColumnPlugin", {"xs_col": 12, "md_col": 4})
            result.config["_cascade_inline"] = deepcopy(inline.glossary)
            self.add_frontend(column, image_plugin.__name__, result.config)

    @staticmethod
    def clear_caches(affected):
        from cms.models import Placeholder
        for pk, language in affected:
            Placeholder.objects.get(pk=pk).clear_cache(language)
