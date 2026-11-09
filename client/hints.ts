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
  key: "hint.quality" | "hint.size" | "hint.sizeRule" | "hint.transparent";
  args: string[];
}

const FIXED_SIZES = new Set(["auto", "1024x1024", "1536x1024", "1024x1536"]);
const SIZE_PATTERN = /^([1-9]\d{1,4})x([1-9]\d{1,4})$/;

/**
 * Whether a free WIDTHxHEIGHT meets the documented rules for gpt-image-2 and
 * the 2.5 models: both sides divisible by 16, an aspect ratio between 1:3 and
 * 3:1, at most 3840×2160.
 */
export function sizeFollowsRules(size: string): boolean {
  const match = SIZE_PATTERN.exec(size);
  if (!match) return true;
  const width = Number(match[1]);
  const height = Number(match[2]);
  const long = Math.max(width, height);
  const short = Math.min(width, height);
  return width % 16 === 0 && height % 16 === 0 && long <= short * 3 && long <= 3840 && width * height <= 3840 * 2160;
}

export function modelHints(choice: ImageChoice): Hint[] {
  const model = (choice.model ?? "").trim().toLowerCase();
  if (!model) return [];
  const is25 = model.startsWith("gpt-image-2.5");
  const is2 = /^gpt-image-2(-\d{4}-\d{2}-\d{2})?$/.test(model);
  const hints: Hint[] = [];
  const quality = (choice.quality ?? "").trim().toLowerCase();
  if ((quality === "xhigh" || quality === "max") && !is25) hints.push({ key: "hint.quality", args: [quality, model] });
  const size = (choice.size ?? "").trim().toLowerCase();
  if (size && !FIXED_SIZES.has(size)) {
    if (!is25 && !is2) hints.push({ key: "hint.size", args: [size, model] });
    else if (!sizeFollowsRules(size)) hints.push({ key: "hint.sizeRule", args: [size] });
  }
  if ((choice.background ?? "").trim().toLowerCase() === "transparent" && is2) {
    hints.push({ key: "hint.transparent", args: [model] });
  }
  return hints;
}
