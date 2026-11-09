// Tool handler of openai-image (`contributes.toolHandler`). Locus hands each
// `image_generate` / `image_edit` call to this module first:
// - With "Image source: Codex subscription" (Plugins → OpenAI Image →
//   Settings; offered only while signed in to Codex), the image is made on the user's
//   Codex subscription through `call.images.generate`; Locus holds the
//   sign-in and saves the file. The Python tool then only records it in
//   history.jsonl and writes the reply, so both modes share one format.
// - Otherwise the Python tool runs as before with the API key, which only
//   it receives (on stdin); this module never sees secret values.

export const CODEX_IMAGES = "codex.images";
/** The subscription endpoint picks these itself (Locus plan 9.6). */
export const IGNORED_ON_CODEX = ["model", "size", "quality", "outputFormat", "n", "inputFidelity"] as const;
export const MAX_CODEX_REFERENCES = 5;
const DEFAULT_OUTPUT_DIR = "Locus/generated/images";

type Args = Record<string, unknown>;

class HandlerError extends Error {}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

/** Same naming as the Python tool: `<yyyyMMdd-HHmmss>-<prompt words>`. */
export function promptSlug(prompt: string): string {
  let slug = "";
  for (const word of prompt.toLowerCase().match(/[\p{L}\p{N}_]+/gu) ?? []) {
    const candidate = slug ? `${slug}-${word}` : word;
    if (candidate.length > 40) break;
    slug = candidate;
  }
  return slug || "image";
}

function stamp(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`;
}

export function fileStem(rawName: unknown, prompt: string, now = new Date()): string {
  const raw = text(rawName);
  if (!raw) return `${stamp(now)}-${promptSlug(prompt)}`;
  if (raw.includes("/") || raw.includes("\\") || raw === "." || raw === "..") {
    throw new HandlerError("fileName is a plain name without folders.");
  }
  const stem = raw.replace(/\.(png|jpe?g|webp)$/i, "").replace(/[<>:"|?*\u0000-\u001f]/g, "-").replace(/^[ .]+|[ .]+$/g, "");
  if (!stem) throw new HandlerError("fileName has no usable characters.");
  return stem.slice(0, 80);
}

/** Arguments the subscription cannot honor, so the reply can say so. */
export function ignoredArgs(args: Args): string[] {
  return IGNORED_ON_CODEX.filter((key) => {
    const value = args[key];
    if (value === undefined || value === null || value === "") return false;
    if (key === "n") return Number(value) !== 1;
    if (key === "size" || key === "quality") return String(value).toLowerCase() !== "auto";
    return true;
  });
}

function references(args: Args): string[] {
  const raw = args.images;
  const list = typeof raw === "string" ? [raw] : Array.isArray(raw) ? raw : [];
  const paths = list.map(text).filter(Boolean);
  if (paths.length === 0) throw new HandlerError("images needs at least one image path.");
  if (paths.length > MAX_CODEX_REFERENCES) {
    throw new HandlerError(
      `The Codex subscription takes at most ${MAX_CODEX_REFERENCES} reference images, got ${paths.length}. `
      + "Pass fewer, or set the image source to API key under Plugins → OpenAI Image → Settings.",
    );
  }
  return paths;
}

async function onCodex(call: any, kind: "generate" | "edit", args: Args) {
  const prompt = text(args.prompt);
  if (!prompt) throw new HandlerError("prompt is required.");
  if (kind === "edit" && text(args.mask)) {
    throw new HandlerError(
      "Masks are not available on the Codex subscription. Describe the change in the prompt instead, "
      + "or set the image source to API key under Plugins → OpenAI Image → Settings.",
    );
  }
  const images = kind === "edit" ? references(args) : undefined;
  const background = (text(args.background) || text(call.settings.defaultBackground) || "auto").toLowerCase();
  const ignored = ignoredArgs(args);

  call.status(kind === "edit" ? "Editing on the Codex subscription" : "Generating on the Codex subscription");
  call.progress("Waiting for Codex (no previews on the subscription)", 0.1);
  const result = await call.images.generate({
    prompt,
    transparentBackground: background === "transparent",
    images,
    outputDir: text(call.settings.outputDir) || DEFAULT_OUTPUT_DIR,
    fileName: fileStem(args.fileName, prompt),
  });
  call.progress("Saving", 0.95);
  // The Python tool records the image and writes the reply (no API call).
  return call.runProcess({ ...args, prompt, codexResult: { ...result, ignored } });
}

export async function handle(call: any, kind: "generate" | "edit") {
  // `codexResult` is internal: never forwarded from the caller.
  const { codexResult: _internal, ...args } = (call.args ?? {}) as Args;
  if (!call.capabilities.granted(CODEX_IMAGES)) return call.runProcess(args);
  try {
    return await onCodex(call, kind, args);
  } catch (error) {
    if (error instanceof HandlerError) return { text: error.message, isError: true };
    throw error;
  }
}

export function tools(ctx: any) {
  ctx.tools.handle("image_generate", (call: any) => handle(call, "generate"));
  ctx.tools.handle("image_edit", (call: any) => handle(call, "edit"));
}
