# Transcription provider and scope menu

## Goal

Make transcription choices easier to scan by grouping them first by provider
(this computer or Colab), then by scope (focused track or all recordings).
Keep model setup, Colab account/settings, and interrupted-job recovery near the
provider they concern. Do not add clip-scoped commands: transcription currently
operates on recordings used by tracks.

## Steps

1. Add menu and command tests for the two provider groups and all-recordings
   Colab action.
2. Add a Colab all-recordings command that reuses existing consent and
   background-job handling.
3. Add English and Finnish provider labels and the new command description.
4. Run CI through GitHub; do not run local tests per the user's instruction.
5. Commit and integrate the completed change with the rescue branch.
