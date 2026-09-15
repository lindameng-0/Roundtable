(function () {
  "use strict";

  var sourceParameter = "from";
  var sourceValue = "roundtable";
  var url = new URL(window.location.href);

  if (url.searchParams.get(sourceParameter) !== sourceValue) return;

  // Remove the transition marker immediately so refreshes and copied links stay clean.
  url.searchParams.delete(sourceParameter);
  window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);

  function showNotice() {
    if (document.querySelector(".roundtable-redirect-notice")) return;

    var dialog = document.createElement("dialog");
    dialog.className = "roundtable-redirect-notice";
    dialog.setAttribute("aria-labelledby", "roundtable-notice-title");
    dialog.setAttribute("aria-describedby", "roundtable-notice-copy");
    dialog.innerHTML = [
      '<form method="dialog" class="roundtable-redirect-notice__body">',
      '<p class="roundtable-redirect-notice__context">You followed a Roundtable link</p>',
      '<h2 id="roundtable-notice-title">Roundtable is now Readerfold.</h2>',
      '<p id="roundtable-notice-copy" class="roundtable-redirect-notice__copy">You\'re in the right place. The site has a new name, and the page you wanted has moved here with it.</p>',
      '<button class="roundtable-redirect-notice__button" value="continue">Continue to Readerfold</button>',
      "</form>"
    ].join("");

    dialog.addEventListener("close", function () { dialog.remove(); }, { once: true });
    document.body.appendChild(dialog);
    dialog.showModal();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", showNotice, { once: true });
  } else {
    showNotice();
  }
}());
