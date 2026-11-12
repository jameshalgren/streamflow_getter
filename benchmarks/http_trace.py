"""Trace HTTP byte-range reads made by fsspec."""

from contextlib import contextmanager
from unittest.mock import patch

from fsspec.implementations.http import HTTPFileSystem


@contextmanager
def trace_http_reads():
    """Record reads through HTTPFileSystem._cat_file.

    This measures returned response-body bytes, not
    total network traffic.
    """
    calls = []
    original = HTTPFileSystem._cat_file

    async def traced(self, url, start=None, end=None, **kwargs):
        result = await original(
            self,
            url,
            start=start,
            end=end,
            **kwargs,
        )

        calls.append({
            "url": url,
            "start": start,
            "end": end,
            "bytes_returned": len(result),
        })

        return result

    with patch.object(HTTPFileSystem, "_cat_file", traced):
        yield calls
@contextmanager
def trace_native_http_reads():
    """Record native HTTPFile range and full-fetch operations.

    Counts bytes returned by instrumented fetch methods,
    not complete network traffic.
    """
    from fsspec.implementations.http import HTTPFile

    calls = []

    original_range = HTTPFile._fetch_range
    original_all = HTTPFile._fetch_all

    def traced_range(self, start, end):
        data = original_range(self, start, end)

        calls.append({
            "kind": "range",
            "start": start,
            "end": end,
            "bytes_returned": len(data),
        })

        return data

    def traced_all(self):
        data = original_all(self)

        calls.append({
            "kind": "full",
            "start": None,
            "end": None,
            "bytes_returned": len(data),
        })

        return data

    with patch.object(
        HTTPFile, "_fetch_range", traced_range
    ), patch.object(
        HTTPFile, "_fetch_all", traced_all
    ):
        yield calls