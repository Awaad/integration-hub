from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from xml.etree.ElementTree import Element, SubElement, tostring



@dataclass
class FeedBuildWarning:
    listing_id: str
    code: str
    message: str



@dataclass(frozen=True)
class Evler101Ad:
    listing_id: str
    fields: dict[str, Any]              # tag -> scalar
    pictures: list[dict[str, Any]]      # [{picture_url, order_by, group_id?}, ...]


def build_101evler_xml(*, ads: Iterable[Evler101Ad]) -> tuple[bytes, list[FeedBuildWarning], int]:
    """
    Build 101evler XML feed from pre-resolved plugin interface ad_projection
    """
    warnings: list[FeedBuildWarning] = []
    root = Element("ads")

    count = 0

    for ad_obj in ads:
        ad_el = SubElement(root, "ad")

        # Emit scalar tags
        for tag, value in ad_obj.fields.items():
            if value is None:
                continue
            SubElement(ad_el, tag).text = str(value)

        # Pictures: must be under <ad_pictures><ad_picture> :contentReference[oaicite:17]{index=17}
        pics_el = SubElement(ad_el, "ad_pictures")
        for pic in ad_obj.pictures:
            if not pic.get("picture_url"):
                continue
            p_el = SubElement(pics_el, "ad_picture")
            SubElement(p_el, "picture_url").text = str(pic["picture_url"])
            SubElement(p_el, "order_by").text = str(pic.get("order_by") or 1)
            if pic.get("group_id") is not None:
                SubElement(p_el, "group_id").text = str(pic["group_id"])  # optional in spec :contentReference[oaicite:18]{index=18}

        count += 1

    xml_bytes = tostring(root, encoding="utf-8", xml_declaration=True)
    return xml_bytes, warnings, count
