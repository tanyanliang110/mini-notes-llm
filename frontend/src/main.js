// main.js — Mini Notes entry point.
//
// Connects to Anna via the runtime SDK loaded from:
//   /static/anna-apps/_sdk/latest/index.js   (global: AnnaAppRuntime)
//
// Real RPC shapes:
//   anna.storage.get({ key })        → { value }
//   anna.storage.set({ key, value })
//   anna.tools.invoke({
//     tool_id: "<executa tool_id>",
//     method: "summarize",
//     args: { notes, max_words },
//   })

import { AnnaAppRuntime } from "/static/anna-apps/_sdk/latest/index.js";
import { init } from "./ui.js";

async function bootstrap() {
  let anna = null;

  try {
    anna = await AnnaAppRuntime.connect();
    console.log("[mini-notes] Connected to Anna runtime");
  } catch (e) {
    console.warn("[mini-notes] Running standalone (no Anna harness):", e?.message || e);
  }

  await init(anna);
}

// Module scripts (type="module") are deferred and execute after DOMContentLoaded.
// So check readyState: if DOM is already ready, bootstrap immediately.
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootstrap);
} else {
  bootstrap();
}
