"""Proves the copy catalogue actually decouples the suite from English.

The tier-1 locators (role + accessible name) bind to visible copy, which is
why the copy lives in one place. These tests are what make that claim real
rather than aspirational: the same page objects drive the same interactions
against every locale in web/i18n/catalog.js, with nothing but the locale
changing.
"""

import pytest
from playwright.sync_api import Browser, expect

from pages import i18n
from pages.demo_page import DemoPage
from pages.i18n import load_catalogs, locales, t


@pytest.fixture
def localized_page(browser: Browser, storage_state_path: str):
    """A logged-in page whose locale is chosen per test. window.__locale must
    be set before any page script runs, hence add_init_script."""
    contexts = []

    def make(locale: str):
        context = browser.new_context(storage_state=storage_state_path)
        context.add_init_script(f"window.__locale = {locale!r};")
        contexts.append(context)
        return context.new_page()

    yield make
    for context in contexts:
        context.close()


def test_every_locale_defines_the_same_keys():
    catalogs = load_catalogs()
    reference = set(catalogs["en"])
    for locale, catalog in catalogs.items():
        assert set(catalog) == reference, f"{locale} key set differs from en"
        assert all(value.strip() for value in catalog.values()), f"{locale} has an empty string"


def test_no_two_locales_share_a_translation():
    """Guards against a locale that was added but never actually translated —
    which would let these tests pass while proving nothing."""
    catalogs = load_catalogs()
    en, zh = catalogs["en"], catalogs["zh"]
    assert not set(en.values()) & set(zh.values())


@pytest.mark.parametrize("locale", locales())
def test_core_interactions_work_in_every_locale(localized_page, demo_server: str, locale: str):
    page = localized_page(locale)
    demo = DemoPage(page, demo_server, locale=locale).open()

    # Every locator below resolves through role + the *localized* accessible
    # name; nothing in this test mentions an English string.
    demo.add_todo("买牛奶")
    expect(demo.todo_items).to_have_text(["买牛奶"])

    demo.click_counter()
    demo.click_counter()
    expect(demo.counter).to_have_text("2")

    demo.toggle_status()
    demo.expect_status(enabled=True)


@pytest.mark.parametrize("locale", locales())
def test_page_renders_the_locale_it_was_given(localized_page, demo_server: str, locale: str):
    page = localized_page(locale)
    DemoPage(page, demo_server, locale=locale).open()
    expect(page.get_by_test_id("add-todo")).to_have_text(t("addTodo", locale))
    expect(page.get_by_test_id("todo-input")).to_have_attribute(
        "placeholder", t("todoPlaceholder", locale)
    )


# -- catalogue reader error paths -------------------------------------------
# t() raises rather than falling back, because a silent fallback would surface
# much later as a locator that mysteriously matches nothing.

def test_unknown_key_raises_and_lists_the_known_ones():
    with pytest.raises(KeyError, match="unknown copy key"):
        t("noSuchKey")


def test_unknown_locale_raises_and_lists_the_known_ones():
    with pytest.raises(KeyError, match="unknown locale"):
        t("addTodo", "kl")


def test_malformed_catalogue_fails_loudly(tmp_path, monkeypatch):
    broken = tmp_path / "catalog.js"
    broken.write_text("// no assignment here\n")
    monkeypatch.setattr(i18n, "CATALOG_PATH", broken)
    i18n.load_catalogs.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="no window.I18N_CATALOGS assignment"):
            i18n.load_catalogs()
    finally:
        i18n.load_catalogs.cache_clear()
