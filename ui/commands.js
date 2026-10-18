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
    register(id, run, { can = null, hintKey = null } = {}) {
      commands.set(id, { run, can, hintKey, planned: false });
    },
    planned(...ids) {
      for (const id of ids)
        commands.set(id, { run: null, can: null, hintKey: null, planned: true });
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
