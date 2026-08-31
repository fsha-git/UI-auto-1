// Single source of truth for every piece of user-visible copy that a test
// depends on. Consumed by BOTH sides:
//
//   - the browser, via web/i18n/apply.js (loaded by each page)
//   - the tests, via pages/i18n.py, which parses the object literal below
//
// That is the whole point: locators built on role + accessible name bind to
// visible copy, so the copy has to live in one place or renaming a button
// silently breaks the suite. Change a string here and both the page and the
// tests follow.
//
// Keep this file pure data with strict JSON syntax inside the braces --
// pages/i18n.py parses it with json.loads and will fail loudly otherwise.
window.I18N_CATALOGS = {
  "en": {
    "todoPlaceholder": "Enter a task",
    "addTodo": "Add",
    "enableFeature": "Enable feature",
    "counterIncrement": "Click me",
    "logout": "Logout",
    "refresh": "Refresh",
    "loginSubmit": "Log in",
    "usernameLabel": "Username",
    "passwordLabel": "Password",
    "invalidCredentials": "Invalid username or password",
    "openProfile": "Open profile",
    "openPopup": "Quick note",
    "popupNotePlaceholder": "Type a note",
    "popupSend": "Send to main page",
    "profileTitle": "Your profile",
    "chartTrend": "Trend chart",
    "chartRegenerate": "Regenerate data",
    "chartSeriesVisits": "Visits",
    "chartSeriesSales": "Sales",
    "chartSeriesErrors": "Errors"
  },
  "zh": {
    "todoPlaceholder": "输入任务",
    "addTodo": "添加",
    "enableFeature": "启用功能",
    "counterIncrement": "点击我",
    "logout": "退出",
    "refresh": "刷新",
    "loginSubmit": "登录",
    "usernameLabel": "用户名",
    "passwordLabel": "密码",
    "invalidCredentials": "用户名或密码错误",
    "openProfile": "打开个人资料",
    "openPopup": "快速便签",
    "popupNotePlaceholder": "输入便签内容",
    "popupSend": "发送到主页面",
    "profileTitle": "你的个人资料",
    "chartTrend": "趋势图",
    "chartRegenerate": "重新生成数据",
    "chartSeriesVisits": "访问量",
    "chartSeriesSales": "销售额",
    "chartSeriesErrors": "错误数"
  }
};
