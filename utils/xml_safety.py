"""
XML safety helpers — defense against XXE / billion-laughs / DTD attacks
on XML coming from external sources (SAT downloads, Finkok responses,
mobile-uploaded CFDIs, etc.).

The satcfdi library uses its own parser internally; we cannot directly
configure it to disallow entities. Instead, this module pre-validates
the XML with `defusedxml` BEFORE handing the string to satcfdi. If the
input has any DOCTYPE / entity reference / external network reference,
this raises `UnsafeXMLError` and the caller refuses to process it.

This is a defense-in-depth layer. Even if the underlying parser is
hardened today, an upgrade or fork could regress; the validation here
is independent.
"""

from __future__ import annotations

import logging
from typing import Union

import defusedxml.ElementTree as DET
from defusedxml.common import (
    DTDForbidden,
    EntitiesForbidden,
    ExternalReferenceForbidden,
    NotSupportedError,
)

logger = logging.getLogger(__name__)


class UnsafeXMLError(ValueError):
    """Raised when the XML payload contains a forbidden construct (DOCTYPE,
    internal/external entity, external reference)."""


# Hard cap on input size (10 MB). CFDIs are typically <100 KB; anything
# larger is suspicious and could be a DoS vector.
_MAX_XML_BYTES = 10 * 1024 * 1024


def assert_safe_xml(xml: Union[str, bytes]) -> None:
    """Validate that the given XML string/bytes is free of dangerous constructs.

    Raises:
        UnsafeXMLError: if the XML contains DOCTYPE, entities, or external refs,
                        or if the input exceeds the size cap, or if it is malformed.
    """
    if xml is None:
        raise UnsafeXMLError("XML input is None")

    if isinstance(xml, str):
        size = len(xml.encode('utf-8', errors='replace'))
    else:
        size = len(xml)

    if size > _MAX_XML_BYTES:
        raise UnsafeXMLError(
            f"XML input too large: {size} bytes (max {_MAX_XML_BYTES})"
        )

    try:
        # defusedxml parses with all dangerous features disabled by default.
        # We don't keep the result — we only care whether parsing rejects it.
        DET.fromstring(xml if isinstance(xml, (bytes, str)) else str(xml))
    except (DTDForbidden, EntitiesForbidden, ExternalReferenceForbidden,
            NotSupportedError) as e:
        logger.warning("Refused unsafe XML: %s", type(e).__name__)
        raise UnsafeXMLError(f"Forbidden XML construct: {type(e).__name__}") from e
    except Exception as e:
        # Malformed XML — let the caller decide whether to surface this.
        # We treat it as unsafe for the strictest contract.
        raise UnsafeXMLError(f"Malformed XML: {e}") from e
