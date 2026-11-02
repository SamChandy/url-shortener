import pytest

from app.services.tracker import lookup_country, parse_user_agent

IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
IPAD = (
    "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
CHROME_WINDOWS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"


@pytest.mark.parametrize(
    "user_agent, device",
    [(IPHONE, "Mobile"), (IPAD, "Tablet"), (CHROME_WINDOWS, "PC"), (GOOGLEBOT, "Other"), ("", "Other")],
)
def test_device_classification(user_agent, device):
    assert parse_user_agent(user_agent)[0] == device


def test_browser_and_os_are_extracted():
    _, browser, os_name = parse_user_agent(CHROME_WINDOWS)
    assert browser == "Chrome" and os_name == "Windows"
    _, browser, os_name = parse_user_agent(IPHONE)
    assert "Safari" in browser and os_name == "iOS"


def test_garbage_user_agents_do_not_crash():
    device, browser, os_name = parse_user_agent("x" * 5000)
    assert device == "Other" and len(browser) <= 64 and len(os_name) <= 64


@pytest.mark.parametrize("ip", [None, "", "not-an-ip", "127.0.0.1", "10.0.0.5", "192.168.1.20", "::1"])
def test_private_or_invalid_ips_have_unknown_country(ip):
    assert lookup_country(ip, "does-not-exist.mmdb") == "Unknown"


def test_public_ip_without_a_geoip_file_is_unknown():
    assert lookup_country("8.8.8.8", "does-not-exist.mmdb") == "Unknown"
