// Draws the structured automix toast (docs/design/TOAST.md) into the notice's rich block
// (index.html #notice-rich). The data comes from automix-toast-model.js; this only puts it
// on the page. The notice's own live region is switched off while the rich block shows: the
// separate #notice-live hears the phase only, not every stage or percent.

export function createAutomixToast(doc = document) {
  const $ = (id) => doc.getElementById(id);
  let announced = "";

  function pips(list) {
    const box = $("nr-pips");
    while (box.children.length > list.length) box.lastElementChild.remove();
    while (box.children.length < list.length) {
      const pip = doc.createElement("span");
      pip.className = "nr-pip";
      box.append(pip);
    }
    list.forEach((item, i) => {
      const pip = box.children[i];
      if (pip.dataset.state !== item.state) pip.dataset.state = item.state;
      pip.title = item.label;
    });
  }

  function text(id, value) {
    const node = $(id);
    if (node.textContent !== value) node.textContent = value;
    node.hidden = value === "";
  }

  return {
    /** Show `view` (rich: true) in the open notice. */
    show(view) {
      const notice = $("notice");
      notice.dataset.layout = "rich";
      notice.setAttribute("aria-live", "off");
      $("notice-rich").hidden = false;
      text("nr-title", view.title);
      text("nr-eta", view.eta);
      text("nr-percent", view.percentText);
      const bar = $("nr-bar");
      if (view.bar.now === null) {
        bar.removeAttribute("aria-valuenow");
        bar.dataset.indeterminate = "";
      } else {
        bar.setAttribute("aria-valuenow", String(view.bar.now));
        delete bar.dataset.indeterminate;
      }
      bar.setAttribute("aria-valuetext", view.bar.valuetext || view.phase);
      $("nr-fill").style.setProperty("--nr-fraction", String(view.bar.fraction));
      text("nr-phase", view.phase);
      text("nr-step", view.step);
      text("nr-track", view.track);
      text("nr-name", view.trackName);
      $("nr-name").title = view.trackName;
      text("nr-note", view.note);
      $("nr-note").title = view.note;
      text("nr-stage", view.stage);
      text("nr-count", view.stageCount);
      pips(view.pips);
      if (view.announce !== announced) {
        announced = view.announce;
        $("notice-live").textContent = announced;
      }
    },
    /** Back to the plain one-line notice. */
    reset() {
      const notice = $("notice");
      if (notice.dataset.layout !== "rich") return;
      notice.dataset.layout = "plain";
      notice.setAttribute("aria-live", "polite");
      $("notice-rich").hidden = true;
      announced = "";
    },
  };
}
