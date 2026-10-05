// Applies the stored theme before the first paint (TASK-35). Served from
// 'self' as a blocking script so the CSP needs no new source or hash.
(function () {
  var root = document.documentElement;
  var choice = "dark";
  try {
    var stored = window.localStorage.getItem("mt-theme");
    if (stored === "light" || stored === "dark" || stored === "system") choice = stored;
  } catch (error) {
    choice = "dark";
  }
  root.setAttribute("data-theme", choice);
})();
