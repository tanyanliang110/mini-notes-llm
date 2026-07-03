// ui.js — DOM rendering and event handling for Mini Notes.

import { loadNotes, addNote, deleteNote } from "./storage.js";
import { summarizeNotes, TOOL_ID, TOOL_METHOD } from "./tools.js";

// DOM element references (lazy init).
let els = {};
let anna = null;

function $(sel) {
  return document.querySelector(sel);
}

function initDomRefs() {
  els = {
    noteInput: $("#note-input"),
    addBtn: $("#add-btn"),
    notesList: $("#notes-list"),
    summarizeBtn: $("#summarize-btn"),
    summaryPanel: $("#summary-panel"),
    summaryText: $("#summary-text"),
    summaryMeta: $("#summary-meta"),
    dismissSummaryBtn: $("#dismiss-summary-btn"),
    errorBanner: $("#error-banner"),
    errorText: $("#error-text"),
    dismissErrorBtn: $("#dismiss-error-btn"),
    connStatus: $("#conn-status"),
    body: document.body,
  };
}

// --- Bootstrap ---

export async function init(annaInstance) {
  anna = annaInstance;
  initDomRefs();
  bindEvents();

  if (anna) {
    setConnStatus(true);
    const notes = await loadNotes(anna);
    renderNotes(notes);
  } else {
    setConnStatus(false);
    renderNotes([]);
  }
}

// --- Event binding ---

function bindEvents() {
  els.addBtn.addEventListener("click", handleAddNote);
  els.noteInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") handleAddNote();
  });
  els.summarizeBtn.addEventListener("click", handleSummarize);
  els.dismissSummaryBtn.addEventListener("click", () => {
    els.summaryPanel.hidden = true;
  });
  els.dismissErrorBtn.addEventListener("click", () => {
    els.errorBanner.hidden = true;
  });
}

// --- Note CRUD ---

async function handleAddNote() {
  const content = els.noteInput.value.trim();
  if (!content) return;

  // addNote() internally calls anna.storage.get() to read current notes
  // from Anna storage, appends the new note, and calls anna.storage.set().
  const newNote = {
    id: Date.now().toString(36) + Math.random().toString(36).slice(2, 8),
    content,
    order: 0, // will be set by addNote after reading current notes
    created_at: new Date().toISOString(),
  };

  try {
    const notes = await addNote(anna, newNote);
    els.noteInput.value = "";
    renderNotes(notes);
  } catch (e) {
    showError(`Failed to save note: ${e?.message || e}`);
  }
}

async function handleDeleteNote(noteId) {
  try {
    // deleteNote() internally calls anna.storage.get() + set().
    const notes = await deleteNote(anna, noteId);
    renderNotes(notes);
  } catch (e) {
    showError(`Failed to delete note: ${e?.message || e}`);
  }
}

// --- Summarize ---

async function handleSummarize() {
  // MUST read current notes from Anna storage, not from local cache.
  const notes = await loadNotes(anna);
  if (notes.length === 0) {
    showError("No notes to summarize. Add some notes first.");
    return;
  }

  setBusy(true);
  els.summarizeBtn.classList.add("btn--loading");
  els.summarizeBtn.disabled = true;

  try {
    const result = await summarizeNotes(anna, notes);
    showSummary(result);
  } catch (e) {
    const msg = e?.message || String(e);
    showError(`Summarize failed: ${msg}`);
    console.error("[ui] summarize error:", msg);
  } finally {
    setBusy(false);
    els.summarizeBtn.classList.remove("btn--loading");
    els.summarizeBtn.disabled = false;
  }
}

// --- Rendering ---

function renderNotes(notes) {
  els.notesList.innerHTML = "";

  if (!notes || notes.length === 0) {
    const li = document.createElement("li");
    li.className = "notes-list__empty";
    li.textContent = "No notes yet. Write one above.";
    els.notesList.appendChild(li);
    return;
  }

  // Sort by order
  const sorted = [...notes].sort((a, b) => (a.order || 0) - (b.order || 0));

  for (const note of sorted) {
    const li = document.createElement("li");
    li.className = "note-item";

    const orderSpan = document.createElement("span");
    orderSpan.className = "note-item__order";
    orderSpan.textContent = `${note.order}.`;

    const contentSpan = document.createElement("span");
    contentSpan.className = "note-item__content";
    contentSpan.textContent = note.content;

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "btn btn--danger";
    deleteBtn.textContent = "Delete";
    deleteBtn.type = "button";
    deleteBtn.addEventListener("click", () => handleDeleteNote(note.id));

    li.append(orderSpan, contentSpan, deleteBtn);
    els.notesList.appendChild(li);
  }
}

function showSummary(result) {
  // Handle both raw tool result and harness-wrapped result
  let data = result;

  // If result has a nested data property (from Executa invoke result)
  if (result && typeof result === "object" && result.data) {
    data = result.data;
  }
  // If result has success + data wrapper
  if (result && typeof result === "object" && result.success && result.data) {
    data = result.data;
  }

  const summary = data?.summary || "(No summary returned)";
  const noteCount = data?.note_count ?? 0;
  const model = data?.model || "unknown model";

  els.summaryText.textContent = summary;
  els.summaryMeta.textContent = `Summarized ${noteCount} notes via ${model}`;
  els.summaryPanel.hidden = false;
}

function showError(message) {
  els.errorText.textContent = message;
  els.errorBanner.hidden = false;
  // Auto-dismiss after 10 seconds
  setTimeout(() => {
    if (els.errorText.textContent === message) {
      els.errorBanner.hidden = true;
    }
  }, 10000);
}

// --- Status helpers ---

function setConnStatus(connected) {
  if (connected) {
    els.connStatus.classList.remove("dot--off");
    els.connStatus.classList.add("dot--on");
    els.connStatus.title = `Connected to Anna | tool: ${TOOL_ID} | method: ${TOOL_METHOD}`;
  } else {
    els.connStatus.classList.remove("dot--on");
    els.connStatus.classList.add("dot--off");
    els.connStatus.title = "Disconnected (standalone preview)";
  }
}

function setBusy(on) {
  els.body.classList.toggle("is-busy", !!on);
}
