"""Translate Cascade Bootstrap 3 glossaries without touching the database."""

from copy import deepcopy
from dataclasses import dataclass, field
import re

# Preserve viewport thresholds: Bootstrap 3 sm/md/lg start at 768/992/1200px.
BREAKPOINTS = {"xs": "xs", "sm": "md", "md": "lg", "lg": "xl"}
TARGETS = {
    "BootstrapContainerPlugin": "GridContainerPlugin",
    "BootstrapRowPlugin": "GridRowPlugin",
    "BootstrapColumnPlugin": "GridColumnPlugin",
    "BootstrapButtonPlugin": "TextLinkPlugin",
    "TextLinkPlugin": "TextLinkPlugin",
    "BootstrapImagePlugin": "ImagePlugin",
    "BootstrapPicturePlugin": "ImagePlugin",
    "BootstrapJumbotronPlugin": "JumbotronPlugin",
    "BootstrapPanelPlugin": "CardPlugin",
    "BootstrapAccordionPlugin": "AccordionPlugin",
    "BootstrapAccordionPanelPlugin": "AccordionItemPlugin",
    "BootstrapTabSetPlugin": "TabPlugin",
    "BootstrapTabPanePlugin": "TabItemPlugin",
    "CarouselPlugin": "CarouselPlugin",
    "CarouselSlidePlugin": "CarouselSlidePlugin",
    "BootstrapGalleryPlugin": "GridRowPlugin",
}
UNSUPPORTED = {"BootstrapSecondaryMenuPlugin": "No equivalent dynamic secondary menu in frontend."}


@dataclass
class Translation:
    target: str
    config: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)


def enabled(value):
    return value is True or value == 1 or value in ("on", "true", "True", "1")


def translate(plugin_type, glossary, parent_glossary=None, first_child=False):
    """Return a config and explicit warnings for features requiring manual review."""
    data = deepcopy(glossary or {})
    parent = parent_glossary or {}
    result = Translation(TARGETS[plugin_type])
    config, warnings = result.config, result.warnings
    used = {"container_max_widths", "media_queries", "breakpoints", "plugin_type"}

    def take(key, default=None):
        used.add(key)
        return data.get(key, default)

    def warn(message):
        if message not in warnings:
            warnings.append(message)

    attrs = deepcopy(take("html_tag_attributes", {}) or {})
    classes = take("extra_css_classes", []) or []
    if isinstance(classes, str):
        classes = classes.split()
    classes = list(classes)
    classes.extend(str(take("css_class", "") or "").split())
    styles = deepcopy(take("inline_styles", {}) or {})
    element_id = take("extra_element_id")
    if element_id:
        attrs["id"] = element_id
    for key, value in data.items():
        if key.startswith("extra_inline_styles:"):
            used.add(key)
            if isinstance(value, dict):
                styles.update(value)
            elif isinstance(value, (list, tuple)) and len(value) == 2:
                if value[0] != "on":
                    styles[key.split(":", 1)[1]] = value[1]
            elif isinstance(value, str):
                styles[key.split(":", 1)[1]] = value
    render_template = take("render_template")
    standard_text_link = plugin_type == "TextLinkPlugin" and render_template == "cascade/link/text-link.html"
    if render_template and not standard_text_link:
        warn("Custom render_template requires a frontend template override.")

    if plugin_type == "BootstrapContainerPlugin":
        config["container_type"] = "container-fluid" if enabled(take("fluid", False)) else "container"
    elif plugin_type == "BootstrapColumnPlugin":
        config["xs_col"] = 12  # Bootstrap 3 stacks unspecified widths; frontend uses flex auto.
        config["text_alignment"] = ""
        for bp, dest in BREAKPOINTS.items():
            for source, target in (("width", "col"), ("offset", "offset")):
                value = take(f"{bp}-column-{source}", "")
                if value:
                    prefix = f"col-{bp}-" + ("offset-" if source == "offset" else "")
                    if not isinstance(value, str) or not re.fullmatch(re.escape(prefix) + r"\d+", value):
                        raise ValueError(f"Invalid {bp} column {source}: {value!r}")
                    number = int(value[len(prefix):])
                    if not (0 if source == "offset" else 1) <= number <= 12:
                        raise ValueError(f"Invalid {bp} column {source}: {value!r}")
                    config[f"{dest}_{target}"] = number
            if take(f"{bp}-column-ordering"):
                warn("Bootstrap 3 push/pull cannot be translated to flex order automatically.")
            visibility = take(f"{bp}-responsive-utils")
            if visibility:
                # The next breakpoint bounds the Bootstrap 3 visibility utility.
                next_bp = {"xs": "md", "sm": "lg", "md": "xl", "lg": None}[bp]
                if visibility == f"hidden-{bp}":
                    classes.append("d-none" if dest == "xs" else f"d-{dest}-none")
                    if next_bp:
                        classes.append(f"d-{next_bp}-block")
                elif isinstance(visibility, str) and visibility.startswith(f"visible-{bp}"):
                    classes += ["d-none", "d-block" if dest == "xs" else f"d-{dest}-block"]
                    if next_bp:
                        classes.append(f"d-{next_bp}-none")
                else:
                    warn(f"Unsupported visibility class: {visibility}")
        if any(data.get(f"{bp}-responsive-utils") for bp in BREAKPOINTS):
            warn("Responsive display utilities need review when multiple visibility rules overlap.")
    elif plugin_type == "BootstrapAccordionPlugin":
        config.update(accordion_flush=False, accordion_header_type="h2")
        take("first_is_open")
        if not enabled(take("close_others", True)):
            warn("Frontend accordions close other items; close_others=False needs a template override.")
    elif plugin_type == "BootstrapAccordionPanelPlugin":
        config.update(accordion_item_header=take("panel_title", ""),
                      accordion_item_open=first_child and enabled(parent.get("first_is_open", True)))
        if take("panel_type") not in (None, "", "panel-default"):
            warn("Accordion panel context colors require custom styling.")
        if take("heading_size"):
            warn("Per-item accordion heading sizes require a template override.")
    elif plugin_type == "BootstrapTabSetPlugin":
        config.update(tab_type="nav-tabs", tab_index=1,
                      tab_alignment="nav-justified" if enabled(take("justified", False)) else "")
    elif plugin_type == "BootstrapTabPanePlugin":
        config["tab_title"] = take("tab_title", "")
    elif plugin_type == "BootstrapPanelPlugin":
        context = str(take("panel_type", "panel-default") or "panel-default").removeprefix("panel-")
        config["card_outline"] = "" if context == "default" else context
        take("heading"), take("footer"), take("heading_size")  # Expanded into card children by the command.
    elif plugin_type == "BootstrapButtonPlugin":
        context = str(take("button_type", "btn-default") or "btn-default").removeprefix("btn-")
        size = take("button_size", "")
        if size == "btn-xs":
            size = "btn-sm"
            warn("Extra-small buttons become small buttons in Bootstrap 5.")
        options = take("button_options", []) or []
        config.update(name=take("link_content", ""), link_type="btn",
                      link_context="secondary" if context == "default" else context,
                      link_size=size, link_block="btn-block" in options)
        if "disabled" in options:
            classes.append("disabled")
            attrs["aria-disabled"] = "true"
        quick_float = take("quick_float")
        if quick_float:
            classes.append({"pull-left": "float-start", "pull-right": "float-end"}.get(quick_float, quick_float))
        if take("symbol") or take("icon_font"):
            warn("Cascade icon fonts need a frontend icon library mapping.")
        take("icon_align")
    elif plugin_type == "TextLinkPlugin":
        config.update(name=take("link_content", ""), link_type="link")
    elif plugin_type == "CarouselPlugin":
        options = take("options", ["slide", "wrap", "pause"]) or []
        config.update(carousel_interval=int(float(take("interval", 5)) * 1000),
                      carousel_wrap="wrap" in options, carousel_pause="hover" if "pause" in options else "false",
                      carousel_transition="" if "slide" in options else "carousel-fade")
        if take("container_max_heights"):
            warn("Responsive carousel heights need custom frontend CSS.")
        if take("resize_options"):
            warn("Carousel image crop/zoom settings need review.")
    elif plugin_type in ("BootstrapImagePlugin", "BootstrapPicturePlugin", "CarouselSlidePlugin"):
        image = take("image")
        config["carousel_image" if plugin_type == "CarouselSlidePlugin" else "picture"] = image
        if image and (not isinstance(image, dict) or not image.get("pk") or not image.get("model")):
            raise ValueError("Image reference must contain a model and pk.")
        attrs["alt"] = take("alt_tag", "")
        if take("image_title"):
            attrs["title"] = data["image_title"]
        options = take("resize_options", []) or []
        if plugin_type != "CarouselSlidePlugin":
            shapes = take("image_shapes", ["img-responsive"]) or []
            config.update(picture_fluid="img-responsive" in shapes,
                          picture_rounded="img-rounded" in shapes,
                          picture_thumbnail="img-thumbnail" in shapes,
                          use_responsive_image="yes", use_crop="crop" in options,
                          use_upscale="upscale" in options)
            if "img-circle" in shapes:
                classes.append("rounded-circle")
            for old, new in (("image_width_fixed", "width"), ("image_height", "height")):
                value = take(old)
                if value and re.fullmatch(r"\d+px", str(value)):
                    config[new] = int(str(value)[:-2])
                elif value:
                    warn(f"{old}={value!r} needs custom sizing.")
            width = take("image_width_responsive")
            if width:
                styles["width"] = width
        if take("responsive_heights") or take("responsive_zoom"):
            warn("Picture art direction and responsive zoom need custom frontend templates.")
        if "high_resolution" in options or "subject_location" in options:
            warn("Retina/subject-location thumbnail behavior differs; review images.")
    elif plugin_type == "BootstrapJumbotronPlugin":
        config["jumbotron_fluid"] = enabled(take("fluid", False))
        for key in ("background_color", "background_repeat", "background_attachment", "background_size"):
            value = take(key)
            if value:
                styles[key.replace("_", "-")] = value
        vertical, horizontal = take("background_vertical_position"), take("background_horizontal_position")
        if vertical or horizontal:
            styles["background-position"] = f"{horizontal or 'center'} {vertical or 'center'}"
        if take("image"):
            config["background_image"] = data["image"]
        if take("container_max_heights") or take("resize_options") or take("background_width_height"):
            warn("Responsive jumbotron background sizing needs review.")
    elif plugin_type == "BootstrapGalleryPlugin":
        warn("Gallery becomes a grid of images; gallery lightbox and thumbnail settings need replacement.")

    if plugin_type in ("BootstrapButtonPlugin", "TextLinkPlugin", "BootstrapImagePlugin", "BootstrapPicturePlugin"):
        link = take("link", {}) or {}
        kind = link.get("type")
        if kind == "exturl":
            config["link"] = {"external_link": link.get("url", "")}
        elif kind == "email":
            config["link"] = {"external_link": "mailto:" + link.get("email", "")}
        elif kind == "cmspage":
            config["link"] = {"internal_link": f"cms.page:{link.get("pk")}"}
            if link.get("section"):
                warn("CMS page section links need manual anchor mapping.")
        elif kind not in (None, "", "none"):
            warn(f"Unsupported link type: {kind}")
        config["target"] = take("target", "")
        if take("title"):
            attrs["title"] = data["title"]

    if classes:
        attrs["class"] = " ".join(filter(None, [attrs.get("class", ""), *classes]))
    if styles:
        attrs["style"] = attrs.get("style", "") + " ".join(f"{key}: {value};" for key, value in styles.items() if value)
    config["attributes"] = attrs
    unmapped = sorted(key for key, value in data.items() if key not in used and value not in (None, "", [], {}))
    if unmapped:
        warn("Settings retained for reference but not rendered: " + ", ".join(unmapped))
    return result
