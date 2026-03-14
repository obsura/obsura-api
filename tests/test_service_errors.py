from __future__ import annotations

from http import HTTPStatus

import pytest

from obsura_api.domain.common import PaginationParams
from obsura_api.domain.errors import UnprocessableContentError
from obsura_api.services.search import SearchService


class DummySession:
    pass


def test_unprocessable_content_error_uses_http_status_name_by_default() -> None:
    error = UnprocessableContentError("Invalid content")

    assert error.status_code == 422
    assert error.code == HTTPStatus(422).name.lower()
    assert error.message == "Invalid content"


def test_search_service_raises_native_error_for_blank_query() -> None:
    service = SearchService(DummySession())

    with pytest.raises(UnprocessableContentError, match="Search query must not be blank"):
        service.search("", PaginationParams(page=1, page_size=10))
