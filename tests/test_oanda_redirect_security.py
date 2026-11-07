"""Security regression: practice bearer token must not follow redirects."""
from urllib.error import HTTPError
from urllib.request import Request, build_opener

import pytest

from norisk_quant.oanda_readonly import _RejectRedirects


@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("destination", [
    "https://synthetic.invalid/collect",
    "http://api-fxpractice.oanda.com/collect",
    "https://api-fxpractice.oanda.com/other-path",
])
def test_practice_redirect_never_constructs_followup_request(code, destination):
    handler = _RejectRedirects()
    request = Request(
        "https://api-fxpractice.oanda.com/v3/instruments/XAU_USD/candles",
        headers={"Authorization": "Bearer FAKE_TEST_TOKEN"},
    )
    with pytest.raises(ValueError, match="redirects are forbidden"):
        handler.redirect_request(request, None, code, "redirect", {}, destination)


def test_practice_default_opener_installs_rejecting_handler():
    opener = build_opener(_RejectRedirects())
    handlers = [h for h in opener.handlers if isinstance(h, _RejectRedirects)]
    assert len(handlers) == 1
