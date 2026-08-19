from playwright.sync_api import Page


class DemoPage:
    def __init__(self, page: Page):
        self.page = page
        self.todo_input = page.locator("#todo-input")
        self.add_btn = page.locator("#add-btn")
        self.todo_list_items = page.locator("#todo-list li")
        self.status_checkbox = page.locator("#status-checkbox")
        self.status_label = page.locator("#status-label")
        self.counter_btn = page.locator("#counter-btn")
        self.counter = page.locator("#counter")
        self.logout_btn = page.locator("#logout-btn")

    def add_todo(self, text: str) -> None:
        self.todo_input.fill(text)
        self.add_btn.click()

    def todo_items(self) -> list[str]:
        return self.todo_list_items.all_text_contents()

    def toggle_checkbox(self) -> None:
        self.status_checkbox.click()

    def status_text(self) -> str:
        return self.status_label.text_content() or ""

    def click_counter(self) -> None:
        self.counter_btn.click()

    def counter_value(self) -> int:
        return int(self.counter.text_content() or "0")

    def logout(self) -> None:
        self.logout_btn.click()
