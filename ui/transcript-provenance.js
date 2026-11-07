const TOOL_KEYS = {
  whisper: "ui.transcript.tool.whisper",
  orukeet: "ui.transcript.tool.orukeet",
  nhsx: "ui.transcript.tool.nhsx",
};

export function provenanceLabel(engine = {}, createdUtc = "", t, formatTime) {
  const backend = engine.backend
    ? t(`ui.transcript.backend.${engine.backend}`)
    : t("ui.transcript.backend.unknown");
  const tool = engine.tool
    ? t(TOOL_KEYS[engine.tool] ?? "ui.transcript.tool.unknown")
    : t("ui.transcript.tool.unknown");
  return t("ui.transcript.provenance", {
    backend,
    tool,
    model: engine.model || t("ui.transcript.model_unknown"),
    language: engine.language || t("ui.transcript.language_unknown"),
    created: formatTime(createdUtc),
  });
}

export function rerunOptions(engine = {}) {
  return {
    backend: engine.backend === "colab" ? "colab" : "local",
    model: engine.model,
    language: engine.language,
    localEngine: engine.tool === "orukeet" ? "orukeet" : "whisper",
  };
}
