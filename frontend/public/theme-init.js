// Runs before the app bundle so the first paint already uses the right theme.
// Choice is "light" | "dark" | "system" (default), saved by the in-app theme toggle.
(function () {
  var choice = "system";
  try {
    choice = localStorage.getItem("sdlc-runbook.theme") || "system";
  } catch (e) {
    /* storage blocked: follow the OS */
  }
  var dark = choice === "dark" || (choice === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
})();
