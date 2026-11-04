// A local transcription request must not start a large model on a machine that
// the engine has already determined is below its minimum memory requirement.
export function transcriptionBackendForMemory(localModelStatus) {
  return localModelStatus?.eligible === true ? "local" : "colab";
}

export async function dispatchTranscription({
  ids,
  backend = "local",
  getLocalStatus,
  transcribeLocal,
  transcribeColab,
  onLowMemory,
}) {
  if (backend === "colab") return transcribeColab(ids);

  const localStatus = await getLocalStatus();
  if (transcriptionBackendForMemory(localStatus) === "colab") {
    onLowMemory?.();
    return transcribeColab(ids);
  }

  return transcribeLocal(ids);
}
