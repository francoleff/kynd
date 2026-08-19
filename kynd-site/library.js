// The Kynd Library — client-side search + category filter.
// No dependencies, no build step. Cards are in the HTML so the page
// works (and indexes) with JS disabled.

(function () {
  "use strict";

  var grid = document.getElementById("grid");
  var input = document.getElementById("q");
  var countEl = document.getElementById("count");
  var emptyEl = document.getElementById("empty");
  if (!grid || !input) return;

  var cards = Array.prototype.slice.call(grid.querySelectorAll(".tool"));
  var chips = Array.prototype.slice.call(document.querySelectorAll(".chip"));
  var total = cards.length;
  var activeFilter = "all";

  function apply() {
    var q = input.value.trim().toLowerCase();
    var terms = q ? q.split(/\s+/) : [];
    var shown = 0;

    cards.forEach(function (card) {
      var haystack = card.getAttribute("data-search") || "";
      var group = card.getAttribute("data-group") || "";
      var passFilter = activeFilter === "all" || group === activeFilter;
      var passSearch = terms.every(function (t) {
        return haystack.indexOf(t) !== -1;
      });
      var visible = passFilter && passSearch;
      card.hidden = !visible;
      if (visible) shown++;
    });

    if (countEl) {
      countEl.textContent =
        shown === total
          ? "Showing all " + total + " tools"
          : "Showing " + shown + " of " + total + " tools";
    }
    if (emptyEl) emptyEl.hidden = shown !== 0;
  }

  input.addEventListener("input", apply);

  chips.forEach(function (chip) {
    chip.addEventListener("click", function () {
      chips.forEach(function (c) {
        c.classList.remove("is-active");
      });
      chip.classList.add("is-active");
      activeFilter = chip.getAttribute("data-filter") || "all";
      apply();
    });
  });

  // "/" focuses search, Escape clears it.
  document.addEventListener("keydown", function (e) {
    if (e.key === "/" && document.activeElement !== input) {
      e.preventDefault();
      input.focus();
    } else if (e.key === "Escape" && document.activeElement === input) {
      input.value = "";
      apply();
    }
  });

  apply();
})();
