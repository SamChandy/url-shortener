"""Streamlit analytics dashboard.

It only talks to the HTTP API (never to the database), so it works against any
deployment: set API_URL to point it somewhere else. Run it with dashboard.bat.
"""
import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:5000").rstrip("/")
TIMEOUT_SECONDS = 10
CACHE_SECONDS = 30  # how long API answers are reused; the Refresh button clears them

st.set_page_config(page_title="Shortly analytics", page_icon="🔗", layout="wide")


# ----------------------------------------------------------------- API access
class ApiProblem(Exception):
    """The API answered with an error, or could not be reached (status 0)."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def error_message(response: requests.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    if not isinstance(body, dict):
        return f"HTTP {response.status_code}"
    message = str(body.get("error", f"HTTP {response.status_code}"))
    if body.get("details"):
        message += " (" + "; ".join(f"{d.get('field')}: {d.get('message')}" for d in body["details"]) + ")"
    return message


def call(method: str, path: str, token: str | None = None, **kwargs: Any) -> Any:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        response = requests.request(method, f"{API_URL}{path}", headers=headers, timeout=TIMEOUT_SECONDS, **kwargs)
    except requests.RequestException:
        raise ApiProblem(0, f"Cannot reach the API at {API_URL}. Is start.bat running?") from None
    if not response.ok:
        raise ApiProblem(response.status_code, error_message(response))
    return response.json()


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def fetch(path: str, token: str, params: dict[str, Any] | None = None) -> Any:
    """Cached GET. Errors raise, and Streamlit never caches an exception."""
    return call("GET", path, token, params=params)


def fail(problem: ApiProblem) -> None:
    if problem.status == 401:  # token expired or invalid
        st.session_state.clear()
        st.session_state["notice"] = "Your session expired. Please log in again."
        st.rerun()
    st.error(problem.message)
    st.stop()


def load(path: str, params: dict[str, Any] | None = None) -> Any:
    try:
        return fetch(path, st.session_state["token"], params)
    except ApiProblem as problem:
        fail(problem)


# --------------------------------------------------------------------- log in
def sign_in(email: str, password: str) -> None:
    data = call("POST", "/api/auth/login", json={"email": email, "password": password})
    st.session_state["token"] = data["access_token"]
    st.session_state["email"] = email.strip().lower()
    st.rerun()


def login_view() -> None:
    st.title("🔗 Shortly analytics")
    if notice := st.session_state.pop("notice", None):
        st.warning(notice)

    log_in_tab, sign_up_tab = st.tabs(["Log in", "Sign up"])
    with log_in_tab:
        with st.form("login"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log in")
        if submitted:
            try:
                sign_in(email, password)
            except ApiProblem as problem:
                st.error(problem.message)

    with sign_up_tab:
        with st.form("signup"):
            email = st.text_input("Email", key="signup_email")
            password = st.text_input("Password (8+ characters)", type="password", key="signup_password")
            submitted = st.form_submit_button("Create account")
        if submitted:
            try:
                call("POST", "/api/auth/signup", json={"email": email, "password": password})
                sign_in(email, password)
            except ApiProblem as problem:
                st.error(problem.message)


# -------------------------------------------------------------------- sidebar
def sidebar() -> None:
    with st.sidebar:
        st.write(f"Logged in as **{st.session_state['email']}**")
        if st.button("Refresh data"):
            st.cache_data.clear()
            st.rerun()
        if st.button("Log out"):
            st.session_state.clear()
            st.cache_data.clear()
            st.rerun()

        st.divider()
        with st.expander("Create a short link"):
            with st.form("create_link", clear_on_submit=True):
                long_url = st.text_input("Long URL", placeholder="https://example.com/some/page")
                alias = st.text_input("Custom alias (optional)")
                has_expiry = st.checkbox("Expires")
                expiry_day = st.date_input("Expiry date", value=date.today() + timedelta(days=7))
                submitted = st.form_submit_button("Create")
            if submitted:
                body: dict[str, Any] = {"long_url": long_url}
                if alias.strip():
                    body["custom_alias"] = alias.strip()
                if has_expiry:
                    body["expires_at"] = datetime.combine(expiry_day, time(23, 59, 59), tzinfo=timezone.utc).isoformat()
                try:
                    created = call("POST", "/api/links", st.session_state["token"], json=body)
                except ApiProblem as problem:
                    st.error(problem.message)
                else:
                    st.cache_data.clear()
                    st.session_state["flash"] = f"Created {created['short_url']}"
                    st.rerun()


# ------------------------------------------------------------------ dashboard
def utc_text(series: pd.Series, missing: str = "") -> pd.Series:
    return pd.to_datetime(series, utc=True).dt.strftime("%Y-%m-%d %H:%M UTC").fillna(missing)


def links_table(links: list[dict[str, Any]], clicks_by_code: dict[str, int]) -> pd.DataFrame:
    df = pd.DataFrame(links)
    df["clicks"] = df["code"].map(clicks_by_code).fillna(0).astype(int)
    df["created"] = utc_text(df["created_at"])
    df["expires"] = utc_text(df["expires_at"], missing="never")
    return df


def charts(code: str, days: int) -> None:
    countries = load(f"/api/analytics/links/{code}/by-country")
    devices = load(f"/api/analytics/links/{code}/by-device")
    per_day = load(f"/api/analytics/links/{code}/per-day", {"days": days})

    left, right = st.columns(2)
    with left:
        country_df = pd.DataFrame(countries).head(15)
        fig = px.bar(country_df, x="country", y="clicks", title="Clicks by country (top 15)")
        fig.update_layout(xaxis_title=None)
        st.plotly_chart(fig)
    with right:
        fig = px.pie(pd.DataFrame(devices), names="device", values="clicks", hole=0.4, title="Clicks by device")
        st.plotly_chart(fig)

    day_df = pd.DataFrame(per_day)
    day_df["date"] = pd.to_datetime(day_df["date"])
    fig = px.line(day_df, x="date", y="clicks", markers=True, title=f"Clicks per day (last {days} days)")
    fig.update_yaxes(rangemode="tozero")
    fig.update_layout(xaxis_title=None)
    st.plotly_chart(fig)


def dashboard_view() -> None:
    sidebar()
    st.title("🔗 My links")
    if flash := st.session_state.pop("flash", None):
        st.success(flash)

    links = load("/api/links", {"limit": 100})
    if not links:
        st.info("You have no links yet. Create one from the sidebar.")
        return
    ranking = load("/api/analytics/top-links", {"limit": 100})
    table = links_table(links, {row["code"]: row["clicks"] for row in ranking})

    first, second, third = st.columns(3)
    first.metric("Links", len(table))
    second.metric("Total clicks", int(table["clicks"].sum()))
    third.metric("Most clicked", table.sort_values("clicks", ascending=False).iloc[0]["code"])

    st.dataframe(
        table[["short_url", "long_url", "clicks", "created", "expires"]],
        hide_index=True,
        column_config={"short_url": st.column_config.LinkColumn("Short link")},
    )
    if len(links) == 100:
        st.caption("Showing your newest 100 links.")

    st.divider()
    by_code = table.set_index("code")
    code = st.selectbox(
        "Choose a link to analyse",
        by_code.index.tolist(),
        format_func=lambda c: f"{c}  →  {by_code.loc[c, 'long_url'][:70]}",
    )
    days = st.slider("Days shown in the per-day chart", 7, 90, 30)
    st.text(f"{by_code.loc[code, 'short_url']}  →  {by_code.loc[code, 'long_url']}")

    total = load(f"/api/analytics/links/{code}/total")["total_clicks"]
    if total == 0:
        st.info(f"No clicks yet. Open {by_code.loc[code, 'short_url']} in your browser, then press Refresh data.")
        return

    top_country = load(f"/api/analytics/links/{code}/by-country")[0]
    top_device = load(f"/api/analytics/links/{code}/by-device")[0]
    a, b, c = st.columns(3)
    a.metric("Total clicks", total)
    b.metric("Top country", top_country["country"], f"{top_country['clicks']} clicks", delta_color="off")
    c.metric("Top device", top_device["device"], f"{top_device['clicks']} clicks", delta_color="off")
    charts(code, days)


# ----------------------------------------------------------------------- main
if "token" not in st.session_state:
    login_view()
else:
    dashboard_view()
