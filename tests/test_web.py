def test_home_page_is_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.mimetype == "text/html"
    body = r.get_data(as_text=True)
    assert "Shortly" in body and "/api/links" in body
    r.close()


def test_home_page_sets_safety_headers(client):
    r = client.get("/")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    r.close()


def test_home_page_does_not_need_login(client):
    r = client.get("/")
    assert r.status_code == 200
    r.close()


def test_short_links_still_work_next_to_the_home_page(client, auth, new_link):
    code = new_link(auth)["code"]
    assert client.get(f"/{code}").status_code == 307


def test_a_trailing_slash_on_a_short_link_still_redirects(client, auth, new_link):
    code = new_link(auth, long_url="https://example.com/target")["code"]
    r = client.get(f"/{code}/")
    assert r.status_code == 307
    assert r.headers["Location"] == "https://example.com/target"
