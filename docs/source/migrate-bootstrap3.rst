Migrate Bootstrap 3 plugins to frontend
======================================

Cascade includes a Django management command, ``convert_bootstrap3``, for moving
stored Bootstrap 3 plugins to ``djangocms-frontend``. It defaults to a read-only
report. The implementation is tested with django CMS 5.1 and frontend 2.5.2.

Preparation
-----------

Install frontend in the Django project containing your CMS database::

    uv add 'djangocms-frontend>=2.5,<3'

Keep ``cmsplugin_cascade`` in ``INSTALLED_APPS`` and enable the target apps::

    INSTALLED_APPS += [
        'djangocms_link',
        'djangocms_frontend',
        'djangocms_frontend.contrib.grid',
        'djangocms_frontend.contrib.link',
        'djangocms_frontend.contrib.image',
        'djangocms_frontend.contrib.card',
        'djangocms_frontend.contrib.accordion',
        'djangocms_frontend.contrib.tabs',
        'djangocms_frontend.contrib.carousel',
        'djangocms_frontend.contrib.jumbotron',
    ]

Only add entries that are not already present. Keep your installed TextPlugin
(e.g. ``djangocms_text_ckeditor``) for panel headings and footers.

Disable the Cascade plugin registrations during conversion::

    CMSPLUGIN_CASCADE_PLUGINS = ()

Cascade and frontend register identical names for carousels and text links;
loading both causes ``PluginAlreadyRegistered`` before the command can start.
The command reads Cascade database rows directly, so it does not need the old
plugin classes registered. Afterwards, re-enable individual Cascade modules
needed for plugins that remain, excluding conflicting carousel and link modules.
If the site uses Cascade's inline ``TextLinkPlugin`` objects, convert those too
with ``--include-text-links``; their plugin name also overlaps frontend. Other
non-Bootstrap Cascade plugin types are outside this command's scope.
A project that uses the optional ``plugin_prefix`` customization must first
normalize its stored plugin types: this command recognizes the standard names.

Run ``uv run python manage.py migrate`` to create the frontend tables. Use
Bootstrap 5 styles/scripts and the frontend template requirements in the target
site. Custom Bootstrap 3 classes and templates need a separate design review.

Run the utility
---------------

Back up the database and review the report before converting a production site.
The command applies to the default database and all placeholders/languages,
including clipboard, draft, published, and versioned content stored as plugins.
It does not rewrite historical django-reversion serialized revisions::

    uv run python manage.py convert_bootstrap3
    uv run python manage.py convert_bootstrap3 --verbosity 2
    uv run python manage.py convert_bootstrap3 --apply

If the report identifies rendering differences, ``--apply`` refuses to commit
unless you explicitly accept them::

    uv run python manage.py convert_bootstrap3 --apply --allow-lossy

Plugins without an equivalent remain unchanged only when explicitly requested::

    uv run python manage.py convert_bootstrap3 --apply --allow-lossy --skip-unsupported

Include existing Cascade inline text links when needed::

    uv run python manage.py convert_bootstrap3 --include-text-links
    uv run python manage.py convert_bootstrap3 --include-text-links --apply --allow-lossy

To migrate only text links (selecting this type also enables their conversion)::

    uv run python manage.py convert_bootstrap3 --plugin-type TextLinkPlugin
    uv run python manage.py convert_bootstrap3 --plugin-type TextLinkPlugin --apply

The standard ``cascade/link/text-link.html`` template uses the frontend default;
custom templates are still reported for review.

Limit a run by repeating placeholder or language filters::

    uv run python manage.py convert_bootstrap3 --placeholder 12 --placeholder 18 --language en

All selected conversions run in one transaction. Errors abort the whole run.
Plugin IDs, languages, placeholders, and existing nested content survive the
conversion. Grid-only conversion leaves tree columns and positions unchanged.
Panels add structural card children and move their existing children into the
card body using the CMS tree APIs. Galleries add columns and images in inline
image order. Repeat runs skip converted plugins, including the carousel types
whose names do not change. Placeholder/page caches are cleared after commit.

The original Cascade rows, shared glossaries, and gallery inlines are retained.
The target config also contains a ``_cascade_migration`` record of the source
settings. These are reference data, not an automatic rollback facility. Restore
the database backup to undo a conversion; do not uninstall Cascade while its
rows and remaining plugin types are still needed.

Mapping and limitations
-----------------------

=============================== ==============================================
Cascade plugin                  Frontend plugin
=============================== ==============================================
BootstrapContainerPlugin        GridContainerPlugin
BootstrapRowPlugin              GridRowPlugin
BootstrapColumnPlugin           GridColumnPlugin
BootstrapButtonPlugin           TextLinkPlugin (button mode)
BootstrapImagePlugin            ImagePlugin
BootstrapPicturePlugin          ImagePlugin
BootstrapPanelPlugin            CardPlugin + CardInnerPlugin + TextPlugin
BootstrapJumbotronPlugin        JumbotronPlugin
BootstrapAccordionPlugin        AccordionPlugin
BootstrapAccordionPanelPlugin   AccordionItemPlugin
BootstrapTabSetPlugin           TabPlugin
BootstrapTabPanePlugin          TabItemPlugin
CarouselPlugin                  CarouselPlugin
CarouselSlidePlugin             CarouselSlidePlugin
BootstrapGalleryPlugin          GridRowPlugin + GridColumnPlugin + ImagePlugin
BootstrapSecondaryMenuPlugin    No equivalent; reported as unsupported
TextLinkPlugin (optional)       TextLinkPlugin (link mode)
=============================== ==============================================

Grid widths and offsets map ``xs -> xs``, ``sm -> md``, ``md -> lg``, and
``lg -> xl`` to retain the 768px, 992px, and 1200px viewport thresholds.
Unspecified mobile widths become 12 units to retain Bootstrap 3 stacking.
Fluid containers, links, image references, titles, classes, element IDs, inline
styles, tab titles, accordion open state, and carousel timing are translated.
Shared settings are materialized in the target config.

The report flags push/pull ordering, overlapping responsive visibility rules,
custom templates, icon fonts, page section links, image art direction/zoom,
responsive carousel heights, background sizing, and other unmapped settings.
They remain available in the source metadata but need manual replacement.
Galleries become image grids; lightbox behavior needs separate implementation.
Container dimensions, gutters, and typography can differ between CSS frameworks.

Test the utility
----------------

The repository's normal suite runs the translation tests without requiring
frontend. To run the optional database integration tests::

    uv run --with 'djangocms-frontend==2.5.2' python -m pytest \
        tests/test_bootstrap3_conversion.py --ds=tests.frontend_settings
