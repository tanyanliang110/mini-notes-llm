// storage.js — Anna storage Host API wrappers for notes persistence.
//
// ALL note read/write operations MUST go through anna.storage.*.
// No localStorage, no IndexedDB, no in-memory-only state.
// The _notesCache is only a rendering mirror — every CRUD operation
// first reads from Anna storage, modifies, and writes back.

const STORAGE_KEY = "mini-notes:items";

// In-memory mirror (kept in sync with Anna storage for rendering only).
let _notesCache = [];

/**
 * Read current notes from Anna storage.
 * Always calls anna.storage.get() — never returns cached data alone.
 */
export async function loadNotes(anna) {
  if (!anna) return [];
  try {
    const result = await anna.storage.get({ key: STORAGE_KEY });
    const value = result?.value;
    if (Array.isArray(value)) {
      _notesCache = value;
      return value;
    }
    // First run / corrupted data — reset via Anna storage.
    await anna.storage.set({ key: STORAGE_KEY, value: [] });
    _notesCache = [];
    return [];
  } catch (e) {
    console.warn("[storage] loadNotes failed:", e?.message || e);
    _notesCache = [];
    return [];
  }
}

/**
 * Save notes to Anna storage.
 * Always calls anna.storage.set() — never stores only in memory.
 */
export async function saveNotes(anna, notes) {
  if (!anna) return;
  _notesCache = notes;
  try {
    await anna.storage.set({ key: STORAGE_KEY, value: notes });
  } catch (e) {
    console.error("[storage] saveNotes failed:", e?.message || e);
    throw e;
  }
}

/**
 * Add a note: reads from Anna storage, appends, writes back.
 * This ensures the "create" flow strictly calls both get and set.
 */
export async function addNote(anna, note) {
  // MUST read current notes from Anna storage first (not from cache).
  const notes = await loadNotes(anna);
  note.order = notes.length + 1;
  notes.push(note);
  await saveNotes(anna, notes);
  return notes;
}

/**
 * Delete a note: reads from Anna storage, filters, writes back.
 * This ensures the "delete" flow strictly calls both get and set.
 */
export async function deleteNote(anna, noteId) {
  // MUST read current notes from Anna storage first (not from cache).
  let notes = await loadNotes(anna);
  notes = notes.filter((n) => n.id !== noteId);
  // Re-index order
  notes.forEach((n, i) => { n.order = i + 1; });
  await saveNotes(anna, notes);
  return notes;
}
