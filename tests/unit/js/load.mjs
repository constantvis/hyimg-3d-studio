// The plugin's modules import three.js from vendor/ by relative paths and run in node as they are (import them straight from the
// repo). What the tests share: the repo's path, a source reader and a fetch stand-in that answers by route and records the calls.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

export const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
export const read = rel => fs.readFileSync(path.join(REPO, rel), "utf8");
export const url = rel => pathToFileURL(path.join(REPO, rel)).href;

// fetch answered by routes(url, opts) -> {status, json?, bytes?} | Error; globalThis.fetch is put back by the returned restore()
export function stubFetch(routes) {
  const calls = [], was = globalThis.fetch;
  globalThis.fetch = async (u, o = {}) => {
    calls.push([String(u), o]);
    const r = await routes(String(u), o, calls.length);
    if (r instanceof Error) throw r;
    const status = r.status || 200;
    return { ok: status < 400, status, json: async () => r.json, text: async () => JSON.stringify(r.json || ""), arrayBuffer: async () => r.bytes || new ArrayBuffer(0), headers: { get: () => null } };
  };
  return { calls, restore: () => { globalThis.fetch = was; } };
}
