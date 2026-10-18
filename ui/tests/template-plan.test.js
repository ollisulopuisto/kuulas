import assert from "node:assert/strict";
import test from "node:test";
import { describePlan, planTemplate } from "../template-plan.js";

test("planTemplate: empty template or empty project", () => {
  assert.deepEqual(planTemplate({}, {}), {
    addTracks: [],
    addClips: [],
    skippedClips: [],
  });
  assert.deepEqual(planTemplate(null, null), {
    addTracks: [],
    addClips: [],
    skippedClips: [],
  });
});

test("planTemplate: adds template tracks that do not exist in project (case-insensitive, trimmed)", () => {
  const template = {
    tracks: [
      { name: "Host", kind: "speech" },
      { name: "Guest", kind: "speech" },
      { name: "Music", kind: "music" },
    ],
    clips: [],
  };
  const project = {
    tracks: [
      { id: "t1", name: "  host  ", kind: "speech", clips: [] }, // matches "Host"
    ],
  };

  const plan = planTemplate(template, project);
  assert.deepEqual(plan.addTracks, [
    { name: "Guest", kind: "speech" },
    { name: "Music", kind: "music" },
  ]);
  assert.deepEqual(plan.addClips, []);
  assert.deepEqual(plan.skippedClips, []);
});

test("planTemplate: adds template clips to existing or added tracks", () => {
  const template = {
    tracks: [
      { name: "Host", kind: "speech" },
      { name: "Intro", kind: "music" },
    ],
    clips: [
      {
        track: "Host",
        media: "sha_host_intro",
        name: "Welcome",
        anchor: 0,
        length: 200,
      },
      {
        track: "Intro",
        media: "sha_music_theme",
        name: "Theme",
        anchor: 0,
        length: 500,
      },
    ],
  };
  const project = {
    tracks: [{ id: "t1", name: "Host", kind: "speech", clips: [] }],
  };

  const plan = planTemplate(template, project);
  // Intro track is added
  assert.deepEqual(plan.addTracks, [{ name: "Intro", kind: "music" }]);
  // Both clips are added
  assert.deepEqual(plan.addClips, [
    {
      track: "Host",
      media: "sha_host_intro",
      name: "Welcome",
      anchor: 0,
      length: 200,
    },
    {
      track: "Intro",
      media: "sha_music_theme",
      name: "Theme",
      anchor: 0,
      length: 500,
    },
  ]);
  assert.deepEqual(plan.skippedClips, []);
});

test("planTemplate: idempotency - clip with same media already on project track is not added", () => {
  const template = {
    tracks: [{ name: "Host", kind: "speech" }],
    clips: [
      {
        track: "Host",
        media: "sha_existing",
        name: "Old Greeting",
        anchor: 0,
        length: 100,
      },
      {
        track: "Host",
        media: "sha_new",
        name: "New Greeting",
        anchor: 100,
        length: 150,
      },
    ],
  };
  const project = {
    tracks: [
      {
        id: "t1",
        name: "Host",
        kind: "speech",
        clips: [{ media: "sha_existing", start: 0, length: 100 }],
      },
    ],
  };

  const plan = planTemplate(template, project);
  assert.deepEqual(plan.addTracks, []);
  // Only the new clip is added; existing media is omitted
  assert.deepEqual(plan.addClips, [
    {
      track: "Host",
      media: "sha_new",
      name: "New Greeting",
      anchor: 100,
      length: 150,
    },
  ]);
  assert.deepEqual(plan.skippedClips, []);
});

test("planTemplate: skips clip whose track name is not in template's own tracks with reason 'no_track'", () => {
  const template = {
    tracks: [{ name: "Host", kind: "speech" }],
    clips: [
      {
        track: "Orphan",
        media: "sha_sfx",
        name: "Chime",
        anchor: 0,
        length: 50,
      },
    ],
  };
  const project = {
    tracks: [{ id: "t1", name: "Host", kind: "speech", clips: [] }],
  };

  const plan = planTemplate(template, project);
  assert.deepEqual(plan.addTracks, []);
  assert.deepEqual(plan.addClips, []);
  assert.deepEqual(plan.skippedClips, [{ media: "sha_sfx", name: "Chime", reason: "no_track" }]);
});

test("planTemplate: skips clip without a media string with reason 'no_media'", () => {
  const template = {
    tracks: [{ name: "Host", kind: "speech" }],
    clips: [
      { track: "Host", media: "", name: "No Media 1", anchor: 0, length: 50 },
      { track: "Host", media: null, name: "No Media 2", anchor: 0, length: 50 },
      { track: "Host", name: "No Media 3", anchor: 0, length: 50 },
      { track: "Host", media: "   ", name: "No Media 4", anchor: 0, length: 50 },
    ],
  };
  const project = { tracks: [] };

  const plan = planTemplate(template, project);
  assert.deepEqual(plan.addTracks, [{ name: "Host", kind: "speech" }]);
  assert.deepEqual(plan.addClips, []);
  assert.deepEqual(plan.skippedClips, [
    { media: "", name: "No Media 1", reason: "no_media" },
    { media: null, name: "No Media 2", reason: "no_media" },
    { media: undefined, name: "No Media 3", reason: "no_media" },
    { media: "   ", name: "No Media 4", reason: "no_media" },
  ]);
});

test("planTemplate: preserves order of added lists following template", () => {
  const template = {
    tracks: [
      { name: "C", kind: "speech" },
      { name: "A", kind: "speech" },
      { name: "B", kind: "music" },
    ],
    clips: [
      { track: "B", media: "sha_b", name: "B Clip", anchor: 0, length: 10 },
      { track: "A", media: "sha_a", name: "A Clip", anchor: 0, length: 10 },
      { track: "C", media: "sha_c", name: "C Clip", anchor: 0, length: 10 },
    ],
  };
  const project = { tracks: [] };

  const plan = planTemplate(template, project);
  assert.deepEqual(
    plan.addTracks.map((t) => t.name),
    ["C", "A", "B"],
  );
  assert.deepEqual(
    plan.addClips.map((c) => c.track),
    ["B", "A", "C"],
  );
});

test("describePlan: counts tracks, clips, skipped", () => {
  const plan = {
    addTracks: [
      { name: "T1", kind: "speech" },
      { name: "T2", kind: "music" },
    ],
    addClips: [{ track: "T1", media: "sha", name: "Clip", anchor: 0, length: 10 }],
    skippedClips: [
      { media: "sha2", name: "Bad1", reason: "no_track" },
      { media: null, name: "Bad2", reason: "no_media" },
      { media: "", name: "Bad3", reason: "no_media" },
    ],
  };

  assert.deepEqual(describePlan(plan), {
    tracks: 2,
    clips: 1,
    skipped: 3,
  });

  assert.deepEqual(describePlan(null), { tracks: 0, clips: 0, skipped: 0 });
});

test("immutability: input template and project are never mutated", () => {
  const template = Object.freeze({
    tracks: Object.freeze([
      Object.freeze({ name: "Host", kind: "speech" }),
      Object.freeze({ name: "Music", kind: "music" }),
    ]),
    clips: Object.freeze([
      Object.freeze({
        track: "Host",
        media: "sha1",
        name: "Voice",
        anchor: 0,
        length: 100,
      }),
      Object.freeze({
        track: "Ghost",
        media: "sha2",
        name: "Skip",
        anchor: 0,
        length: 50,
      }),
    ]),
  });
  const project = Object.freeze({
    tracks: Object.freeze([
      Object.freeze({
        id: "t1",
        name: "Host",
        kind: "speech",
        clips: Object.freeze([Object.freeze({ media: "sha1", start: 0, length: 100 })]),
      }),
    ]),
  });

  const plan = planTemplate(template, project);
  assert.equal(plan.addTracks.length, 1);
  assert.equal(plan.addClips.length, 0);
  assert.equal(plan.skippedClips.length, 1);
  assert.deepEqual(describePlan(plan), { tracks: 1, clips: 0, skipped: 1 });
});
