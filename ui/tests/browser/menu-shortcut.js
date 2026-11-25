import { createMenubar } from "../../menubar.js";

createMenubar({
  root: document.getElementById("menubar"),
  getMenus: () => [
    {
      id: "edit",
      label: "Muokkaa",
      items: [
        {
          id: "range.scope_toggle",
          label: "Alueen muokkaukset: kaikki raidat / vain valitut raidat",
          keys: "⌘⇧A",
          enabled: true,
        },
        { id: "undo", label: "Kumoa", keys: "⌘Z", enabled: true },
      ],
    },
  ],
  run: () => {},
  t: (key) => key,
});
document.querySelector(".menu-title").click();
const rows = [...document.querySelectorAll(".menu-item")].map((button) => {
  const label = button.firstElementChild.getBoundingClientRect();
  const key = button.querySelector("kbd").getBoundingClientRect();
  const range = document.createRange();
  range.selectNodeContents(button.firstElementChild);
  const first = range.getClientRects()[0];
  return {
    labelTop: label.top,
    firstTop: first.top,
    keyTop: key.top,
    keyRight: key.right,
    rowRight: button.getBoundingClientRect().right,
  };
});
document.getElementById("result").textContent = JSON.stringify(rows);
