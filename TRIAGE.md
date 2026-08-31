# Test Triage Report

Suite run against each injected-bug page.

## bug_add_dedupes_items.html
**Caught by:**
- `test_add_duplicate_todo_items_are_both_kept[chromium]`

## bug_add_empty_allowed.html
**Caught by:**
- `test_add_empty_todo_item_is_ignored[chromium]`
- `test_add_whitespace_only_todo_item_is_ignored[chromium]`

## bug_add_todo_noop.html
**Caught by:**
- `test_add_todo_item[chromium]`
- `test_add_todo_html_is_rendered_as_text_not_markup[chromium]`
- `test_add_very_long_todo_item_is_not_truncated[chromium]`
- `test_add_duplicate_todo_items_are_both_kept[chromium]`

## bug_add_truncates_long_text.html
**Caught by:**
- `test_add_very_long_todo_item_is_not_truncated[chromium]`

## bug_add_uses_innerhtml.html
**Caught by:**
- `test_add_todo_html_is_rendered_as_text_not_markup[chromium]`

## bug_add_whitespace_allowed.html
**Caught by:**
- `test_add_whitespace_only_todo_item_is_ignored[chromium]`

## bug_checkbox_label_static.html
**Caught by:**
- `test_checkbox_toggle[chromium]`
- `test_checkbox_toggle_parity_over_multiple_clicks[chromium]`

## bug_checkbox_skip_every_third_toggle.html
**Caught by:**
- `test_checkbox_toggle_parity_over_multiple_clicks[chromium]`

## bug_counter_increments_by_two.html
**Caught by:**
- `test_counter_increment[chromium]`
- `test_counter_increment_many_times[chromium]`

## bug_counter_noop.html
**Caught by:**
- `test_counter_increment[chromium]`
- `test_counter_increment_many_times[chromium]`

## bug_title_mismatch.html
**Caught by:**
- `test_page_title[chromium]`

## bug_win_popup_no_close.html
**Caught by:**
- `test_popup_sends_note_back_to_opener[chromium]`

## bug_win_popup_result_noop.html
**Caught by:**
- `test_popup_sends_note_back_to_opener[chromium]`

## bug_win_profile_count_static.html
**Caught by:**
- `test_profile_page_shows_live_todo_count[chromium]`

## bug_win_profile_link_same_tab.html
**Caught by:**
- `test_profile_link_opens_a_new_tab[chromium]`
- `test_profile_page_shows_live_todo_count[chromium]`

