import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { readOnlyBanner } from "../read-only-model.js";

const NOTE = { host: "Studio-Mac", user: "olli", opened_utc: "2026-10-23T11:05:00Z" };
const opts = { locale: "fi-FI", timeZone: "Europe/Helsinki" };

describe("readOnlyBanner: who holds a project that is open read-only", () => {
  test("nothing for a project you can edit", () => {
    assert.equal(readOnlyBanner(null, opts), null);
    assert.equal(readOnlyBanner(undefined, opts), null);
  });

  test("names the user, the machine and the time with its zone", () => {
    const banner = readOnlyBanner(NOTE, opts);
    assert.equal(banner.key, "ui.readonly.banner");
    assert.equal(banner.values.user, "olli");
    assert.equal(banner.values.host, "Studio-Mac");
    // 11:05 UTC is 14:05 in Helsinki in October (EEST until 25 Oct 2026).
    assert.match(banner.values.since, /14[.:]05/);
    assert.match(banner.values.since, /GMT\+3|UTC\+3|EEST/);
  });

  test("without a user name it still says where", () => {
    const banner = readOnlyBanner({ ...NOTE, user: "" }, opts);
    assert.equal(banner.key, "ui.readonly.banner_no_user");
    assert.equal(banner.values.user, undefined);
  });

  test("an unreadable time is left out rather than shown as 'Invalid Date'", () => {
    const banner = readOnlyBanner({ ...NOTE, opened_utc: "" }, opts);
    assert.equal(banner.key, "ui.readonly.banner_no_time");
    assert.equal(banner.values.since, undefined);
  });
});
