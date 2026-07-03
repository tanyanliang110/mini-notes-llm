// tools.js — Anna tools.invoke Host API wrapper for the summarize Executa.

// Local-dev fallback tool_id; matches executa.json tool_id.
const DEV_FALLBACK_TOOL_ID = "mini-notes-summarize";

// Resolved tool_id: uses published id if available (window.__ANNA_TOOL_IDS__),
// otherwise falls back to the dev placeholder.
export const TOOL_ID =
  (typeof window !== "undefined" &&
    window.__ANNA_TOOL_IDS__ &&
    window.__ANNA_TOOL_IDS__["summarize"]) ||
  DEV_FALLBACK_TOOL_ID;

// The method name on the Executa tool (matches MANIFEST.tools[0].name).
export const TOOL_METHOD = "summarize";

// Call the summarize Executa tool via Anna Host API.
// Returns the tool result { success, tool, data: { summary, note_count, model, usage } }.
export async function summarizeNotes(anna, notes) {
  if (!anna) throw new Error("Not connected to Anna runtime");

  const result = await anna.tools.invoke({
    tool_id: TOOL_ID,
    method: TOOL_METHOD,
    args: {
      notes: notes.map((n, i) => ({ content: n.content, order: i + 1 })),
      max_words: 100,
    },
  });

  return result;
}
