// The command registry: every command by id, filled in by app.js. The keys,
// the palette, the cheat sheet and the menus all read it, so a command exists
// once. `can(state)` is a pure predicate (false when it cannot apply: nothing
// to undo, no selection); `hintKey` is a translated one-line description.
// A command with no function yet is "planned": listed everywhere, never run.

export function createRegistry() {
  const commands = new Map();
  const listeners = [];
  return {
    /** `fn(id)` is called after a command ran (not for one that could not apply). */
    onRun(fn) {
      listeners.push(fn);
    },
    /**
     * `why(state)` makes it an edit key: when `can` says no, it returns the reason ({ key, values })
     * the key shows instead of failing silently (edit-reasons.js), and the key is handled, not beeped.
     */
    register(id, run, { can = null, hintKey = null, why = null } = {}) {
      commands.set(id, { run, can, hintKey, why, planned: false });
    },
    planned(...ids) {
      for (const id of ids)
        commands.set(id, { run: null, can: null, hintKey: null, why: null, planned: true });
    },
    /** Mark every id that has no command as planned. */
    planMissing(ids) {
      for (const id of ids) if (!commands.has(id)) this.planned(id);
    },
    has: (id) => commands.has(id),
    status(id) {
      const command = commands.get(id);
      return command && !command.planned ? "ready" : "planned";
    },
    hintKey: (id) => commands.get(id)?.hintKey ?? null,
    /** Can it apply to this state? Planned: never. A predicate that throws counts as no. */
    can(id, state) {
      const command = commands.get(id);
      if (!command || command.planned) return false;
      if (!command.can) return true;
      try {
        return Boolean(command.can(state));
      } catch {
        return false;
      }
    },
    /** Is it an edit key: one that tells the user why it did nothing? */
    explains(id) {
      const command = commands.get(id);
      return Boolean(command && !command.planned && command.why);
    },
    /** Why it cannot apply to this state: { key, values? }, or null when it can (or does not say). */
    why(id, state) {
      const command = commands.get(id);
      if (!command?.why || this.can(id, state)) return null;
      try {
        return command.why(state) ?? null;
      } catch {
        return null;
      }
    },
    /** Run it. With a state, a command that cannot apply is not run. Returns whether it ran. */
    run(id, event, state) {
      const command = commands.get(id);
      if (!command || command.planned) return false;
      if (state !== undefined && !this.can(id, state)) return false;
      command.run(event);
      for (const listener of listeners) {
        try {
          listener(id);
        } catch {
          // A listener (the recent list) must never undo a command that ran.
        }
      }
      return true;
    },
    ids: () => [...commands.keys()],
  };
}
