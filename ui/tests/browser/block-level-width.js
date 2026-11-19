// Long imported speaker names must not squeeze block rows (owner, 2026-11-19).

const lists = document.getElementById("lists");
for (const name of [
  "Olli",
  "2026-11-19-t03-04-25pm-guest232006--panu",
  "2026-11-19-t00-karde--conversation",
]) {
  const field = document.createElement("fieldset");
  field.className = "form-fieldset";
  const legend = document.createElement("legend");
  legend.className = "form-label";
  legend.textContent = name;
  const choices = document.createElement("div");
  choices.className = "form-choices";
  for (let i = 0; i < 4; i++) {
    const label = document.createElement("label");
    label.className = "form-choice block-level-choice";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = true;
    const span = document.createElement("span");
    span.className = "block-level-line";
    span.textContent =
      "1:52–2:01 · mitattu −24,0 dB · +4,3 dB puhujan tasosta · käytä vahvistusta −4,3 dB";
    label.append(box, span);
    choices.append(label);
  }
  field.append(legend, choices);
  lists.append(field);
}
// Layout reads force style calculation; a hidden/occluded headless tab need not
// deliver animation frames merely to measure this static fixture.
document.getElementById("result").textContent = JSON.stringify(
  [...document.querySelectorAll(".block-level-line")].map((n) =>
    Math.round(n.getBoundingClientRect().width),
  ),
);
