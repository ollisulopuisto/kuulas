// The remembered choices and validation for Track > Auto > Duck music.
export const DEFAULTS = Object.freeze({
  style: "gaps",
  ratio: 8,
  threshold_db: -30,
  attack_ms: 50,
  release_ms: 300,
});

const ranges = {
  ratio: [1, 20],
  threshold_db: [-60, 0],
  attack_ms: [1, 500],
  release_ms: [10, 2000],
};

function number(value) {
  const text = String(value ?? "")
    .trim()
    .replace(",", ".");
  if (!/^[-+]?(\d+\.?\d*|\.\d+)$/.test(text)) return Number.NaN;
  return Number(text);
}

export function normaliseSettings(value) {
  const saved = value && typeof value === "object" ? value : {};
  const result = { ...DEFAULTS };
  result.style = saved.style === "sidechain" ? "sidechain" : "gaps";
  for (const [key, [low, high]] of Object.entries(ranges)) {
    const candidate = number(saved[key]);
    if (candidate >= low && candidate <= high) result[key] = candidate;
  }
  return result;
}

export function reductionAtReference(ratio, thresholdDb, referenceDb = -19) {
  return referenceDb > thresholdDb ? -(referenceDb - thresholdDb) * (1 - 1 / ratio) : 0;
}

export function validateSettings(form) {
  const errors = {};
  const values = {};
  if (form.style !== "gaps" && form.style !== "sidechain") errors.style = "ui.duck_music.bad_style";
  for (const [key, [low, high]] of Object.entries(ranges)) {
    const parsed = number(form[key]);
    if (parsed >= low && parsed <= high) values[key] = parsed;
    else if (form.style === "sidechain") errors[key] = "ui.duck_music.bad_number";
    else values[key] = DEFAULTS[key];
  }
  return {
    ok: Object.keys(errors).length === 0,
    errors,
    options: {
      style: form.style,
      ratio: values.ratio,
      threshold_db: values.threshold_db,
      attack_s: values.attack_ms / 1000,
      release_s: values.release_ms / 1000,
    },
  };
}
