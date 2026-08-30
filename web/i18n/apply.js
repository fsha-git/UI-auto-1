// Fills every [data-i18n] / [data-i18n-placeholder] element from the catalog.
//
// Locale comes from window.__locale, which tests set with add_init_script
// before any page script runs; it defaults to English. Applying on
// DOMContentLoaded means the text is in place before page.goto() resolves
// (goto waits for `load`, which fires later), so there is no window in which
// a role+name locator would miss.
(function () {
  var locale = window.__locale || "en";
  var catalog = window.I18N_CATALOGS[locale] || window.I18N_CATALOGS.en;
  window.I18N = catalog;

  function apply() {
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      var value = catalog[el.dataset.i18n];
      if (value !== undefined) el.textContent = value;
    });
    document.querySelectorAll("[data-i18n-placeholder]").forEach(function (el) {
      var value = catalog[el.dataset.i18nPlaceholder];
      if (value !== undefined) el.placeholder = value;
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", apply);
  } else {
    apply();
  }
})();
