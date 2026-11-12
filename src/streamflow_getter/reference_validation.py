
"""Validation of operational NWM Kerchunk references."""

REQUIRED_KEYS = {
    ".zgroup",
    "feature_id/.zarray",
    "feature_id/0",
    "streamflow/.zarray",
    "streamflow/0",
}

ALLOWED_SCHEMES = ("https://", "http://", "s3://")


def resolve_reference_url(url, templates=None):
    """Resolve a direct URL or a single Kerchunk URL template."""
    if not isinstance(url, str):
        return None

    if url.startswith(ALLOWED_SCHEMES):
        return url if "{{" not in url and "}}" not in url else None

    if not isinstance(templates, dict):
        return None

    if not (url.startswith("{{") and url.endswith("}}")):
        return None

    name = url[2:-2]

    if not name or "{{" in name or "}}" in name:
        return None

    resolved = templates.get(name)

    if not isinstance(resolved, str):
        return None

    if not resolved.startswith(ALLOWED_SCHEMES):
        return None

    if "{{" in resolved or "}}" in resolved:
        return None

    return resolved


def valid_byte_range(value, templates=None) -> bool:
    """Check a Kerchunk external byte-range reference."""
    if not isinstance(value, list) or len(value) != 3:
        return False

    url, offset, length = value

    if resolve_reference_url(url, templates) is None:
        return False

    if type(offset) is not int or offset < 0:
        return False

    if type(length) is not int or length <= 0:
        return False

    return True


def validate_reference(reference) -> bool:
    """Validate direct and templated NWM Kerchunk references."""
    if not isinstance(reference, dict):
        return False

    if reference.get("version") != 1:
        return False

    refs = reference.get("refs")

    if not isinstance(refs, dict):
        return False

    if not REQUIRED_KEYS.issubset(refs):
        return False

    templates = reference.get("templates", {})

    if not isinstance(templates, dict):
        return False

    for value in refs.values():
        if isinstance(value, list):
            if not valid_byte_range(value, templates):
                return False
        elif not isinstance(value, str):
            return False

    return True


def valid_source_identity(reference, expected_url) -> bool:
    """Verify that all external chunks use the expected NWM source."""
    if not isinstance(expected_url, str) or not expected_url:
        return False

    if not validate_reference(reference):
        return False

    templates = reference.get("templates", {})

    for value in reference["refs"].values():
        if isinstance(value, list):
            resolved = resolve_reference_url(value[0], templates)

            if resolved != expected_url:
                return False

    return True
