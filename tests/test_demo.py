from playwright.sync_api import Page, expect

from pages.demo_page import DemoPage


def test_page_title(demo_page: DemoPage, page: Page):
    expect(page).to_have_title("UI Automation Demo Page")


def test_add_todo_item(demo_page: DemoPage):
    demo_page.add_todo("Buy milk")
    demo_page.add_todo("Write tests")
    expect(demo_page.todo_items).to_have_text(["Buy milk", "Write tests"])


def test_checkbox_toggle(demo_page: DemoPage):
    demo_page.expect_status(enabled=False)
    demo_page.toggle_status()
    demo_page.expect_status(enabled=True)
    demo_page.toggle_status()
    demo_page.expect_status(enabled=False)


def test_counter_increment(demo_page: DemoPage):
    expect(demo_page.counter).to_have_text("0")
    demo_page.click_counter()
    demo_page.click_counter()
    demo_page.click_counter()
    expect(demo_page.counter).to_have_text("3")


# --- Negative tests ---

def test_add_empty_todo_item_is_ignored(demo_page: DemoPage):
    demo_page.add_todo("")
    expect(demo_page.todo_items).to_have_count(0)


def test_add_whitespace_only_todo_item_is_ignored(demo_page: DemoPage):
    demo_page.add_todo("   ")
    expect(demo_page.todo_items).to_have_count(0)


def test_add_todo_html_is_rendered_as_text_not_markup(demo_page: DemoPage):
    payload = "<script>window.__xss = true;</script>"
    demo_page.add_todo(payload)
    expect(demo_page.todo_items).to_have_text([payload])
    # confirm no actual <script> element was injected into the DOM
    assert demo_page.injected_script_count() == 0
    assert demo_page.xss_flag() is None


# --- Boundary tests ---

def test_add_very_long_todo_item_is_not_truncated(demo_page: DemoPage):
    long_text = "a" * 1000
    demo_page.add_todo(long_text)
    expect(demo_page.todo_items).to_have_text([long_text])


def test_add_duplicate_todo_items_are_both_kept(demo_page: DemoPage):
    demo_page.add_todo("Buy milk")
    demo_page.add_todo("Buy milk")
    expect(demo_page.todo_items).to_have_text(["Buy milk", "Buy milk"])


def test_counter_increment_many_times(demo_page: DemoPage):
    for _ in range(50):
        demo_page.click_counter()
    expect(demo_page.counter).to_have_text("50")


def test_checkbox_toggle_parity_over_multiple_clicks(demo_page: DemoPage):
    for _ in range(5):
        demo_page.toggle_status()
    # 5 (odd) toggles from OFF should land on ON
    demo_page.expect_status(enabled=True)
    demo_page.toggle_status()
    # one more (6th, even) toggle should land back on OFF
    demo_page.expect_status(enabled=False)
