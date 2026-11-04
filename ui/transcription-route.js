// A local transcription request must not start a large model on a machine that
// the engine has already determined is below its minimum memory requirement.
export function transcriptionBackendForMemory(localModelStatus) {
  return localModelStatus?.eligible === true ? "local" : "colab";
}
