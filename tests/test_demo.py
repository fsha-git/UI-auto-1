from pages.demo_page import DemoPage


def test_page_title(demo_page: DemoPage):
    assert demo_page.page.title() == "UI Automation Demo Page"


def test_add_todo_item(demo_page: DemoPage):
    demo_page.add_todo("Buy milk")
    demo_page.add_todo("Write tests")
    assert demo_page.todo_items() == ["Buy milk", "Write tests"]


def test_checkbox_toggle(demo_page: DemoPage):
    assert demo_page.status_text() == "Status: OFF"
    demo_page.toggle_checkbox()
    assert demo_page.status_text() == "Status: ON"
    demo_page.toggle_checkbox()
    assert demo_page.status_text() == "Status: OFF"


def test_counter_increment(demo_page: DemoPage):
    assert demo_page.counter_value() == 0
    demo_page.click_counter()
    demo_page.click_counter()
    demo_page.click_counter()
    assert demo_page.counter_value() == 3


# --- Negative tests ---

def test_add_empty_todo_item_is_ignored(demo_page: DemoPage):
    demo_page.add_todo("")
    assert demo_page.todo_items() == []


def test_add_whitespace_only_todo_item_is_ignored(demo_page: DemoPage):
    demo_page.add_todo("   ")
    assert demo_page.todo_items() == []


def test_add_todo_html_is_rendered_as_text_not_markup(demo_page: DemoPage):
    payload = "<script>window.__xss = true;</script>"
    demo_page.add_todo(payload)
    assert demo_page.todo_items() == [payload]
    # confirm no actual <script> element was injected into the DOM
    assert demo_page.page.locator("#todo-list script").count() == 0
    assert demo_page.page.evaluate("window.__xss") is None


# --- Boundary tests ---

def test_add_very_long_todo_item_is_not_truncated(demo_page: DemoPage):
    long_text = "a" * 1000
    demo_page.add_todo(long_text)
    assert demo_page.todo_items() == [long_text]


def test_add_duplicate_todo_items_are_both_kept(demo_page: DemoPage):
    demo_page.add_todo("Buy milk")
    demo_page.add_todo("Buy milk")
    assert demo_page.todo_items() == ["Buy milk", "Buy milk"]


def test_counter_increment_many_times(demo_page: DemoPage):
    for _ in range(50):
        demo_page.click_counter()
    assert demo_page.counter_value() == 50


def test_checkbox_toggle_parity_over_multiple_clicks(demo_page: DemoPage):
    for _ in range(5):
        demo_page.toggle_checkbox()
    # 5 (odd) toggles from OFF should land on ON
    assert demo_page.status_text() == "Status: ON"
    demo_page.toggle_checkbox()
    # one more (6th, even) toggle should land back on OFF
    assert demo_page.status_text() == "Status: OFF"
