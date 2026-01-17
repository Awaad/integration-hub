from __future__ import annotations
import hashlib
from typing import Iterable
from xml.etree.ElementTree import Element, SubElement, tostring

from app.canonical.v1.listing import ListingCanonicalV1

# Minimal XML feed generator for listings 
def generate_xml_feed(listings: Iterable[ListingCanonicalV1]) -> tuple[bytes, str, int]:
    root = Element("listings")

    count = 0
    for l in listings:
        count += 1
        item = SubElement(root, "listing")
        SubElement(item, "id").text = l.canonical_id
        SubElement(item, "title").text = l.title
        SubElement(item, "status").text = l.status
        if l.list_price:
            SubElement(item, "currency").text = l.list_price.currency
            SubElement(item, "amount").text = str(l.list_price.amount)

        # minimal address
        if l.address:
            addr = SubElement(item, "address")
            if l.address.city:
                SubElement(addr, "city").text = l.address.city
            if l.address.country:
                SubElement(addr, "country").text = l.address.country

    data = tostring(root, encoding="utf-8", xml_declaration=True)
    h = hashlib.sha256(data).hexdigest()
    return data, h, count
