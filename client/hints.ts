// Parameter combinations a model may reject, per the openai-python parameter
// notes (checked 2026-11-06). Only hints: the API stays the judge and its
// error is shown as is. Image Studio keeps a copy of these rules.

export interface ImageChoice {
  model?: string;
  size?: string;
  quality?: string;
  background?: string;
}

export interface Hint {
  key: "hint.quality" | "hint.size" | "hint.transparent";
  args: string[];
}

const FIXED_SIZES = new Set(["auto", "1024x1024", "1536x1024", "1024x1536"]);

export function modelHints(choice: ImageChoice): Hint[] {
  const model = (choice.model ?? "").trim().toLowerCase();
  if (!model) return [];
  const is25 = model.startsWith("gpt-image-2.5");
  const is2 = /^gpt-image-2(-\d{4}-\d{2}-\d{2})?$/.test(model);
  const hints: Hint[] = [];
  const quality = (choice.quality ?? "").trim().toLowerCase();
  if ((quality === "xhigh" || quality === "max") && !is25) hints.push({ key: "hint.quality", args: [quality, model] });
  const size = (choice.size ?? "").trim().toLowerCase();
  if (size && !FIXED_SIZES.has(size) && !is25 && !is2) hints.push({ key: "hint.size", args: [size, model] });
  if ((choice.background ?? "").trim().toLowerCase() === "transparent" && is2) {
    hints.push({ key: "hint.transparent", args: [model] });
  }
  return hints;
}
