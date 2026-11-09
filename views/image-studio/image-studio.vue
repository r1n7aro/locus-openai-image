<view>
{ "name": "Image Studio", "icon": "image" }
</view>

<script setup lang="ts">
// Image Studio: a chat-style page for generating and editing images with the
// plugin's own tools. Each generation is a turn: the prompt (and reference
// images) on the right, the result on the left. The composer at the bottom
// holds the prompt, the references dropped from the file tree and the
// options (model, size, quality, background, format, count).
//
// Generation runs through view.plugin.tools.call (caller "view"), so it
// streams partial images and shows up in the status icon like calls by the
// model. When the user allowed the Codex subscription (Plugins → OpenAI
// Image → Settings) the same tools run on it and the composer
// only offers what the subscription honors. Finished turns come from
// history.jsonl in the output folder, so images made by the model appear
// here too; failed or cancelled turns stay until the View closes.
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, toRaw, watch } from "vue";
import { useLocusFileDropTarget, useViewState, view } from "@locus/view-runtime";
import { BaseButton, BaseDropdown, BaseSegmented } from "@locus/components";

const messages: Record<string, Record<string, string>> = {
  en: {
    notPlugin: "This View belongs to the OpenAI Image plugin and only works when the plugin is enabled for the workspace.",
    tabChat: "Chat",
    tabGallery: "Gallery",
    modeApi: "API key",
    modeCodex: "Codex subscription",
    settings: "Settings",
    refresh: "Refresh",
    missingKey: "The OpenAI API key is not set.",
    openSettings: "Open settings",
    codexMode: "Codex subscription: the server picks model, size and quality (currently 1536×1024) and there are no previews. Only the prompt, background and up to 5 references take effect.",
    emptyTitle: "Describe an image to start",
    emptyHint: "Drop images from the file tree onto the box below to edit or combine them.",
    promptPlaceholder: "Describe the image… (Enter to send, Shift+Enter for a new line)",
    promptPlaceholderEdit: "Describe what to change in the references… (Enter to send)",
    send: "Generate",
    sendEdit: "Edit",
    stop: "Stop",
    dropHere: "Drop images to use them as references",
    mask: "Mask",
    maskHint: "Transparent pixels of the mask mark the area of the first image to change.",
    useAsMask: "Use as mask",
    remove: "Remove",
    model: "Model",
    modelCustom: "Custom model…",
    modelCustomPlaceholder: "Model name",
    modelList: "Choose from the list",
    modelDefault: "default",
    hintFlare: "faster",
    hintSunburst: "higher quality",
    groupOther: "Other",
    groupCustom: "Custom",
    size: "Size",
    width: "Width",
    height: "Height",
    groupAllModels: "All models",
    groupFlexible: "gpt-image-2 and 2.5 only",
    "size.auto": "Auto",
    "size.1024x1024": "Square · 1024×1024",
    "size.1536x1024": "Landscape 3:2 · 1536×1024",
    "size.1024x1536": "Portrait 2:3 · 1024×1536",
    "size.1536x864": "Wide 16:9 · 1536×864",
    "size.864x1536": "Tall 9:16 · 864×1536",
    "size.3840x2160": "4K 16:9 · 3840×2160",
    "size.custom": "Custom…",
    quality: "Quality",
    "quality.auto": "Auto",
    "quality.low": "Low",
    "quality.medium": "Medium",
    "quality.high": "High",
    "quality.xhigh": "Extra high",
    "quality.max": "Max",
    background: "Background",
    "background.auto": "Auto",
    "background.opaque": "Opaque",
    "background.transparent": "Transparent",
    format: "Format",
    count: "Count",
    countOne: "1 image",
    countMany: "{0} images",
    transparentJpeg: "Transparent backgrounds need PNG or WebP.",
    sizeInvalid: "Enter the size as width × height.",
    codexNoMask: "Masks are not available on the Codex subscription.",
    codexTooMany: "The Codex subscription takes at most {0} reference images.",
    "hint.quality": "{0} quality is only documented for the gpt-image-2.5 models; {1} may reject it.",
    "hint.size": "Custom sizes like {0} are only documented for gpt-image-2 and the 2.5 models; {1} may reject it.",
    "hint.sizeRule": "{0} may be rejected: custom sizes need both sides divisible by 16, an aspect ratio between 1:3 and 3:1, and at most 3840×2160.",
    "hint.transparent": "Transparent backgrounds are a preview feature on {0}.",
    waiting: "Waiting for the first preview…",
    waitingCodex: "Waiting for Codex…",
    cancelled: "Cancelled.",
    retry: "Retry",
    editThis: "Edit this image",
    reuse: "Reuse settings",
    copyPath: "Copy path",
    copied: "Copied",
    fromAgent: "By the model",
    sourceCodex: "Codex subscription",
    seconds: "{0} s",
    earlier: "Show earlier",
    gallery: "Gallery",
    galleryEmpty: "Generated images appear here.",
    galleryMissing: "No history in {0} yet.",
    more: "Show more",
    close: "Close",
    revised: "Revised prompt",
    references_: "References",
    unreadable: "Image not readable",
  },
  zh: {
    notPlugin: "这个 View 属于 OpenAI Image 插件，需要在工作区启用插件后使用。",
    tabChat: "对话",
    tabGallery: "图库",
    modeApi: "API Key",
    modeCodex: "Codex 订阅",
    settings: "设置",
    refresh: "刷新",
    missingKey: "还没有设置 OpenAI API Key。",
    openSettings: "打开设置",
    codexMode: "Codex 订阅模式：服务端决定模型、尺寸和质量（目前为 1536×1024），没有中间预览。只有提示词、背景和最多 5 张参考图生效。",
    emptyTitle: "描述一张图片开始生成",
    emptyHint: "把文件树里的图片拖到下方输入框，可以编辑或合成。",
    promptPlaceholder: "描述想要的图片…（Enter 发送，Shift+Enter 换行）",
    promptPlaceholderEdit: "描述要对参考图做的修改…（Enter 发送）",
    send: "生成",
    sendEdit: "编辑",
    stop: "停止",
    dropHere: "松开即可添加为参考图",
    mask: "蒙版",
    maskHint: "蒙版中透明的像素表示第一张参考图里要修改的区域。",
    useAsMask: "设为蒙版",
    remove: "移除",
    model: "模型",
    modelCustom: "自定义模型…",
    modelCustomPlaceholder: "模型名称",
    modelList: "从列表选择",
    modelDefault: "默认",
    hintFlare: "更快",
    hintSunburst: "质量更高",
    groupOther: "其他",
    groupCustom: "自定义",
    size: "尺寸",
    width: "宽",
    height: "高",
    groupAllModels: "所有模型",
    groupFlexible: "仅 gpt-image-2 和 2.5 系列",
    "size.auto": "自动",
    "size.1024x1024": "方形 · 1024×1024",
    "size.1536x1024": "横向 3:2 · 1536×1024",
    "size.1024x1536": "纵向 2:3 · 1024×1536",
    "size.1536x864": "宽屏 16:9 · 1536×864",
    "size.864x1536": "竖屏 9:16 · 864×1536",
    "size.3840x2160": "4K 16:9 · 3840×2160",
    "size.custom": "自定义…",
    quality: "质量",
    "quality.auto": "自动",
    "quality.low": "低",
    "quality.medium": "中",
    "quality.high": "高",
    "quality.xhigh": "很高",
    "quality.max": "最高",
    background: "背景",
    "background.auto": "自动",
    "background.opaque": "不透明",
    "background.transparent": "透明",
    format: "格式",
    count: "张数",
    countOne: "1 张",
    countMany: "{0} 张",
    transparentJpeg: "透明背景需要 PNG 或 WebP 格式。",
    sizeInvalid: "请按 宽 × 高 填写尺寸。",
    codexNoMask: "Codex 订阅模式不支持蒙版。",
    codexTooMany: "Codex 订阅模式最多支持 {0} 张参考图。",
    "hint.quality": "{0} 质量只写明了 gpt-image-2.5 系列支持，{1} 可能会拒绝。",
    "hint.size": "{0} 这类自定义尺寸只写明了 gpt-image-2 和 2.5 系列支持，{1} 可能会拒绝。",
    "hint.sizeRule": "{0} 可能会被拒绝：自定义尺寸要求两边都是 16 的倍数、宽高比在 1:3 到 3:1 之间、不超过 3840×2160。",
    "hint.transparent": "透明背景在 {0} 上还是预览功能。",
    waiting: "等待第一张预览…",
    waitingCodex: "等待 Codex 生成…",
    cancelled: "已取消。",
    retry: "重试",
    editThis: "以此编辑",
    reuse: "复用设置",
    copyPath: "复制路径",
    copied: "已复制",
    fromAgent: "由模型生成",
    sourceCodex: "Codex 订阅",
    seconds: "{0} 秒",
    earlier: "显示更早的记录",
    gallery: "图库",
    galleryEmpty: "生成的图片会显示在这里。",
    galleryMissing: "{0} 中还没有历史记录。",
    more: "显示更多",
    close: "关闭",
    revised: "改写后的提示词",
    references_: "参考图",
    unreadable: "无法读取图片",
  },
};

const plugin = view.plugin;
const lang = computed(() => (String(plugin?.locale ?? "en").toLowerCase().startsWith("zh") ? "zh" : "en"));
function tr(key: string, ...args: unknown[]): string {
  const text = messages[lang.value][key] ?? messages.en[key] ?? key;
  return text.replace(/\{(\d+)\}/g, (_, index) => String(args[Number(index)] ?? ""));
}

const IMAGE_EXT = /\.(png|jpe?g|webp)$/i;
const CODEX_IMAGES = "codex.images";
const MAX_CODEX_REFERENCES = 5;
const MAX_REFERENCES = 16;
const CUSTOM = "__custom__";
/** Sizes every model accepts. */
const FIXED_SIZES = ["auto", "1024x1024", "1536x1024", "1024x1536"];
/** Common sizes for the models that accept any WIDTHxHEIGHT. */
const FLEXIBLE_SIZES = ["1536x864", "864x1536", "3840x2160"];
const SIZE_PATTERN = /^([1-9]\d{1,4})x([1-9]\d{1,4})$/;
const MIME: Record<string, string> = { png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", webp: "image/webp" };
const TURN_PAGE = 20;
const TILE_PAGE = 48;

// ── composer ────────────────────────────────────────────────────────────

const form = useViewState({
  initialized: false,
  prompt: "",
  model: "",
  modelMode: "list" as "list" | "custom",
  size: "auto",
  sizeMode: "preset" as "preset" | "custom",
  customSize: "1280x720",
  quality: "auto",
  background: "auto",
  outputFormat: "png",
  n: "1",
  references: [] as string[],
  mask: "",
}, "form");

const tab = ref<"chat" | "gallery">("chat");
const settings = ref<Record<string, any>>({});
const keyConfigured = ref(true);
const modelSuggestions = ref<string[]>([]);
/** The user allowed the Codex subscription for this plugin. */
const onCodex = ref(false);
/** Problems outside a turn (loading settings, copying a path). */
const error = ref<string | null>(null);

/** Granted and usable: a grant needs a Codex sign-in (`available`). */
function codexActive(list: any[]): boolean {
  return list.some((capability) =>
    capability.name === CODEX_IMAGES && capability.granted && capability.available !== false);
}

async function loadCapabilities() {
  if (!plugin) return;
  const list = await plugin.capabilities.get();
  onCodex.value = codexActive(list);
}

function applySize(value: string) {
  const size = String(value || "auto").trim().toLowerCase();
  if ([...FIXED_SIZES, ...FLEXIBLE_SIZES].includes(size)) {
    form.size = size;
    form.sizeMode = "preset";
  } else {
    form.customSize = size;
    form.sizeMode = "custom";
  }
}

async function loadSettings() {
  if (!plugin) return;
  const state = await plugin.settings.get();
  const values: Record<string, any> = {};
  for (const item of state.settings) {
    values[item.name] = item.value;
    if (item.name === "apiKey") keyConfigured.value = item.configured === true;
    if (item.name === "model") modelSuggestions.value = (item.kind as any)?.suggestions ?? [];
  }
  const outputChanged = settings.value.outputDir !== values.outputDir;
  settings.value = values;
  if (!form.initialized) {
    form.model = values.model ?? "";
    applySize(values.defaultSize ?? "auto");
    form.quality = values.defaultQuality ?? "auto";
    form.background = values.defaultBackground ?? "auto";
    form.outputFormat = values.defaultFormat ?? "png";
    form.initialized = true;
  }
  if (outputChanged) await loadHistory();
}

// Model: the suggestions grouped by family, plus any name typed in.
function modelFamily(name: string): string {
  const match = /^gpt-image-(\d+(?:\.\d+)?)/i.exec(name);
  return match ? `GPT Image ${match[1]}` : tr("groupOther");
}

function modelHint(name: string): string {
  const hints: string[] = [];
  if (/flare/i.test(name)) hints.push(tr("hintFlare"));
  if (/sunburst/i.test(name)) hints.push(tr("hintSunburst"));
  if (name === settings.value.model) hints.push(tr("modelDefault"));
  return hints.join(" · ");
}

const modelOptions = computed(() => {
  const names = [...new Set([...modelSuggestions.value, settings.value.model].filter((name): name is string => Boolean(name)))];
  const families: string[] = [];
  const byFamily = new Map<string, string[]>();
  for (const name of names) {
    const family = modelFamily(name);
    if (!byFamily.has(family)) {
      byFamily.set(family, []);
      families.push(family);
    }
    byFamily.get(family)!.push(name);
  }
  const options = families.flatMap((family) =>
    byFamily.get(family)!.map((name) => ({ value: name, label: name, hint: modelHint(name), group: family })));
  const typed = form.model.trim();
  if (typed && !names.includes(typed)) options.push({ value: typed, label: typed, hint: "", group: tr("groupCustom") });
  options.push({ value: CUSTOM, label: tr("modelCustom"), hint: "", group: tr("groupCustom") });
  return options;
});

function chooseModel(value: string) {
  if (value === CUSTOM) {
    form.modelMode = "custom";
    void nextTick(() => modelInputEl.value?.focus());
    return;
  }
  form.model = value;
  form.modelMode = "list";
}

const modelInputEl = ref<HTMLInputElement | null>(null);
const modelLabel = computed(() => form.model.trim() || String(settings.value.model || ""));

// Size: fixed sizes, common free sizes, or any width × height.
const effectiveSize = computed(() => String((form.sizeMode === "custom" ? form.customSize : form.size) ?? "auto").trim().toLowerCase());
const sizeOptions = computed(() => [
  ...FIXED_SIZES.map((value) => ({ value, label: tr(`size.${value}`), group: tr("groupAllModels") })),
  ...FLEXIBLE_SIZES.map((value) => ({ value, label: tr(`size.${value}`), group: tr("groupFlexible") })),
  { value: CUSTOM, label: tr("size.custom"), group: tr("groupFlexible") },
]);
const sizeChoice = computed(() => (form.sizeMode === "custom" ? CUSTOM : form.size));

function chooseSize(value: string) {
  if (value === CUSTOM) {
    form.sizeMode = "custom";
    return;
  }
  form.size = value;
  form.sizeMode = "preset";
}

function sizeSide(index: 1 | 2): string {
  const sides = String(form.customSize ?? "").trim().toLowerCase().split("x");
  return (sides[index - 1] ?? "").trim();
}

function setSizeSide(index: 1 | 2, raw: string) {
  const width = index === 1 ? raw.trim() : sizeSide(1);
  const height = index === 2 ? raw.trim() : sizeSide(2);
  form.customSize = `${width}x${height}`;
}

const sizeLabel = computed(() => {
  const size = effectiveSize.value;
  if (form.sizeMode === "custom") return size.replace("x", "×");
  return size === "auto" ? tr("size.auto") : size.replace("x", "×");
});

const qualityOptions = computed(() =>
  ["auto", "low", "medium", "high", "xhigh", "max"].map((value) => ({ value, label: tr(`quality.${value}`) })));
const backgroundOptions = computed(() =>
  ["auto", "opaque", "transparent"].map((value) => ({ value, label: tr(`background.${value}`) })));
const formatOptions = [
  { value: "png", label: "PNG" },
  { value: "jpeg", label: "JPEG" },
  { value: "webp", label: "WebP" },
];
const countOptions = computed(() =>
  ["1", "2", "3", "4"].map((value) => ({ value, label: value === "1" ? tr("countOne") : tr("countMany", value) })));
const labelOf = (options: { value: string; label: string }[], value: string) =>
  options.find((option) => option.value === value)?.label ?? value;
const chip = (name: string, value: string) => `${tr(name)} · ${value}`;

const isEdit = computed(() => form.references.length > 0);
const formError = computed(() => {
  if (onCodex.value) {
    if (form.mask) return tr("codexNoMask");
    if (form.references.length > MAX_CODEX_REFERENCES) return tr("codexTooMany", MAX_CODEX_REFERENCES);
    return null;
  }
  if (form.sizeMode === "custom" && !SIZE_PATTERN.test(effectiveSize.value)) return tr("sizeInvalid");
  return form.background === "transparent" && form.outputFormat === "jpeg" ? tr("transparentJpeg") : null;
});

/** Whether a free WIDTHxHEIGHT meets the documented rules. */
function sizeFollowsRules(size: string): boolean {
  const match = SIZE_PATTERN.exec(size);
  if (!match) return true;
  const width = Number(match[1]);
  const height = Number(match[2]);
  const long = Math.max(width, height);
  const short = Math.min(width, height);
  return width % 16 === 0 && height % 16 === 0 && long <= short * 3 && long <= 3840 && width * height <= 3840 * 2160;
}

// Combinations a model may reject (same rules as client/hints.ts). Only
// hints: the API stays the judge and its error is shown as is.
const hints = computed(() => {
  if (onCodex.value) return [];
  const model = modelLabel.value.toLowerCase();
  if (!model) return [];
  const is25 = model.startsWith("gpt-image-2.5");
  const is2 = /^gpt-image-2(-\d{4}-\d{2}-\d{2})?$/.test(model);
  const size = effectiveSize.value;
  const list: string[] = [];
  if ((form.quality === "xhigh" || form.quality === "max") && !is25) list.push(tr("hint.quality", form.quality, model));
  if (size && !FIXED_SIZES.includes(size) && SIZE_PATTERN.test(size)) {
    if (!is25 && !is2) list.push(tr("hint.size", size, model));
    else if (!sizeFollowsRules(size)) list.push(tr("hint.sizeRule", size));
  }
  if (form.background === "transparent" && is2) list.push(tr("hint.transparent", model));
  return list;
});

const running = ref<{ controller: AbortController; turn: Turn } | null>(null);
const canGenerate = computed(() =>
  Boolean(plugin) && !running.value && form.prompt.trim().length > 0 && !formError.value);

// The prompt box grows with its text up to a limit.
const promptEl = ref<HTMLTextAreaElement | null>(null);
function fitPrompt() {
  const element = promptEl.value;
  if (!element) return;
  element.style.height = "auto";
  element.style.height = `${Math.min(element.scrollHeight, 200)}px`;
}
watch(() => form.prompt, () => void nextTick(fitPrompt));

function onPromptKeydown(event: KeyboardEvent) {
  if (event.key !== "Enter" || event.isComposing) return;
  if (event.shiftKey && !(event.ctrlKey || event.metaKey)) return;
  event.preventDefault();
  void generate();
}

// ── references ──────────────────────────────────────────────────────────

function addReference(path: string) {
  if (!IMAGE_EXT.test(path) || form.references.includes(path) || form.mask === path) return;
  if (form.references.length >= MAX_REFERENCES) return;
  form.references.push(path);
  void ensureUrl(path);
}

function removeReference(path: string) {
  form.references.splice(form.references.indexOf(path), 1);
}

function useAsMask(path: string) {
  removeReference(path);
  form.mask = path;
}

// File drops are broadcast to the whole window; only those released over
// the composer belong here (the chat input does the same).
const composerEl = ref<HTMLElement | null>(null);

function insideComposer(x?: number, y?: number): boolean {
  const bounds = composerEl.value?.getBoundingClientRect();
  if (!bounds || !bounds.width || !Number.isFinite(x) || !Number.isFinite(y)) return false;
  return x! >= bounds.left && x! <= bounds.right && y! >= bounds.top && y! <= bounds.bottom;
}

const drop = useLocusFileDropTarget({
  onDrop: (files: { path: string; isDir: boolean }[], payload: { x?: number; y?: number }) => {
    if (!insideComposer(payload?.x, payload?.y)) return;
    for (const file of files) if (!file.isDir) addReference(file.path);
  },
});
const dragOver = computed(() => {
  const state = drop.dragState.value as { active?: boolean; x?: number; y?: number } | null;
  return Boolean(state?.active) && insideComposer(state?.x, state?.y);
});
const isPng = (path: string) => path.toLowerCase().endsWith(".png");
const fileName = (path: string) => path.split(/[\\/]/).pop() ?? path;

// ── image loading ───────────────────────────────────────────────────────

const urls = reactive<Record<string, string>>({});
const unreadable = reactive<Record<string, boolean>>({});
const pending = new Map<string, Promise<void>>();
let activeReads = 0;
const queue: (() => void)[] = [];

function mimeOf(path: string): string {
  return MIME[path.split(".").pop()?.toLowerCase() ?? ""] ?? "image/png";
}

async function readBlobUrl(path: string): Promise<string> {
  const bytes = await view.fs.readFile(path);
  return URL.createObjectURL(new Blob([bytes as Uint8Array], { type: mimeOf(path) }));
}

function ensureUrl(path: string): Promise<void> {
  if (urls[path] || unreadable[path]) return Promise.resolve();
  const existing = pending.get(path);
  if (existing) return existing;
  const task = new Promise<void>((resolve) => {
    const start = () => {
      activeReads += 1;
      readBlobUrl(path)
        .then((url) => { urls[path] = url; })
        .catch(() => { unreadable[path] = true; })
        .finally(() => {
          activeReads -= 1;
          pending.delete(path);
          queue.shift()?.();
          resolve();
        });
    };
    if (activeReads < 3) start();
    else queue.push(start);
  });
  pending.set(path, task);
  return task;
}

// Images load when they scroll into view.
const observer = typeof IntersectionObserver === "undefined"
  ? null
  : new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      const path = (entry.target as HTMLElement).dataset.path;
      if (path) void ensureUrl(path);
      observer?.unobserve(entry.target);
    }
  }, { rootMargin: "300px" });

const vLazy = {
  mounted(element: HTMLElement, binding: { value: string }) {
    element.dataset.path = binding.value;
    if (observer) observer.observe(element);
    else void ensureUrl(binding.value);
  },
  beforeUnmount(element: HTMLElement) {
    observer?.unobserve(element);
  },
};

// ── history and turns ───────────────────────────────────────────────────

interface HistoryEntry {
  id: string;
  createdAt: string;
  tool?: string;
  caller?: string;
  callId?: string;
  prompt: string;
  revisedPrompt?: string | null;
  model?: string;
  size?: string;
  quality?: string;
  background?: string;
  outputFormat?: string;
  path: string;
  references?: string[];
  durationMs?: number;
  /** `codex` (Codex subscription) or `apiKey`; absent in entries of 0.1. */
  source?: string;
}

interface Turn {
  id: string;
  createdAt: string;
  prompt: string;
  references: string[];
  mask?: string;
  caller?: string;
  source?: string;
  model?: string;
  size?: string;
  quality?: string;
  outputFormat?: string;
  durationMs?: number;
  revisedPrompt?: string | null;
  images: HistoryEntry[];
  /** Reply text of a local turn that saved no file. */
  text?: string;
  status: "done" | "running" | "error" | "cancelled";
  error?: string;
  message?: string;
  progress?: number | null;
  partialUrl?: string | null;
  /** Local turns: the call, for retrying. */
  tool?: string;
  args?: Record<string, unknown>;
}

const history = ref<HistoryEntry[]>([]);
const historyMissing = ref(false);
const localTurns = ref<Turn[]>([]);
const shownTurns = ref(TURN_PAGE);
const shownTiles = ref(TILE_PAGE);
const selected = ref<HistoryEntry | null>(null);
const copied = ref<string | null>(null);

const outputDir = computed(() => String(settings.value.outputDir || "Locus/generated/images"));

async function loadHistory() {
  try {
    const text = await view.fs.readFile(view.path.join(outputDir.value, "history.jsonl"), "utf8");
    const entries: HistoryEntry[] = [];
    for (const line of String(text).split("\n")) {
      if (!line.trim()) continue;
      try {
        const entry = JSON.parse(line);
        if (entry && typeof entry.path === "string") entries.push(entry);
      } catch {
        /* skip a damaged line */
      }
    }
    history.value = entries;
    historyMissing.value = false;
  } catch {
    history.value = [];
    historyMissing.value = true;
  }
}

/** Consecutive history lines of one call (n > 1) form one turn. */
const historyTurns = computed<Turn[]>(() => {
  const turns: Turn[] = [];
  for (const entry of history.value) {
    const last = turns[turns.length - 1];
    if (last && entry.callId && last.id === entry.callId) {
      last.images.push(entry);
      continue;
    }
    turns.push({
      id: entry.callId || entry.id,
      createdAt: entry.createdAt,
      prompt: entry.prompt,
      references: entry.references ?? [],
      caller: entry.caller,
      source: entry.source,
      model: entry.model,
      size: entry.size,
      quality: entry.quality,
      outputFormat: entry.outputFormat,
      durationMs: entry.durationMs,
      revisedPrompt: entry.revisedPrompt,
      images: [entry],
      status: "done",
    });
  }
  return turns;
});

const turns = computed(() => [...historyTurns.value, ...localTurns.value]
  .map((turn, index) => ({ turn, index, time: Date.parse(turn.createdAt) || 0 }))
  .sort((left, right) => left.time - right.time || left.index - right.index)
  .map((item) => item.turn));
const visibleTurns = computed(() => turns.value.slice(Math.max(0, turns.value.length - shownTurns.value)));
const galleryEntries = computed(() => [...history.value].reverse());
const visibleTiles = computed(() => galleryEntries.value.slice(0, shownTiles.value));

function turnModel(turn: Turn): string {
  return turn.source === "codex" || turn.model === "codex" ? tr("sourceCodex") : turn.model || "";
}

function turnMeta(turn: Turn): string {
  const parts = [turnModel(turn)];
  if (turn.size) parts.push(turn.size.replace("x", "×"));
  if (turn.quality) parts.push(tr(`quality.${turn.quality}`));
  if (turn.outputFormat) parts.push(turn.outputFormat.toUpperCase());
  if (turn.durationMs) parts.push(tr("seconds", (turn.durationMs / 1000).toFixed(1)));
  return parts.filter(Boolean).join(" · ");
}

// ── scrolling ───────────────────────────────────────────────────────────

const threadEl = ref<HTMLElement | null>(null);
let stickToBottom = true;

function onThreadScroll() {
  const element = threadEl.value;
  if (!element) return;
  stickToBottom = element.scrollHeight - element.scrollTop - element.clientHeight < 80;
}

function scrollToBottom(force = false) {
  if (!force && !stickToBottom) return;
  void nextTick(() => {
    const element = threadEl.value;
    if (element) element.scrollTop = element.scrollHeight;
    stickToBottom = true;
  });
}

watch(() => turns.value.length, () => scrollToBottom());
watch(tab, (value) => {
  if (value === "chat") scrollToBottom(true);
});

// ── generation ──────────────────────────────────────────────────────────

let localSeq = 0;

function buildCall(): { tool: string; args: Record<string, unknown> } {
  const prompt = form.prompt.trim();
  // On the subscription only the honored arguments are sent.
  const args: Record<string, unknown> = onCodex.value
    ? { prompt, background: form.background }
    : {
      prompt,
      size: effectiveSize.value,
      quality: form.quality,
      background: form.background,
      outputFormat: form.outputFormat,
      n: Number(form.n),
    };
  const model = form.model.trim();
  if (!onCodex.value && model && model !== settings.value.model) args.model = model;
  if (isEdit.value) {
    args.images = [...form.references];
    if (form.mask && !onCodex.value) args.mask = form.mask;
  }
  return { tool: isEdit.value ? "image_edit" : "image_generate", args };
}

async function generate() {
  if (!plugin || !canGenerate.value) return;
  const { tool, args } = buildCall();
  const turn = reactive<Turn>({
    id: `local-${++localSeq}`,
    createdAt: new Date().toISOString(),
    prompt: String(args.prompt),
    references: [...form.references],
    mask: form.mask || undefined,
    caller: "view",
    source: onCodex.value ? "codex" : "apiKey",
    model: onCodex.value ? "codex" : modelLabel.value,
    size: onCodex.value ? undefined : effectiveSize.value,
    quality: onCodex.value ? undefined : form.quality,
    outputFormat: onCodex.value ? undefined : form.outputFormat,
    images: [],
    status: "running",
    tool,
    args,
  }) as Turn;
  localTurns.value.push(turn);
  form.prompt = "";
  form.references.splice(0);
  form.mask = "";
  scrollToBottom(true);
  await run(turn);
}

function setPartial(turn: Turn, url: string | null) {
  if (turn.partialUrl) URL.revokeObjectURL(turn.partialUrl);
  turn.partialUrl = url;
}

const sameFile = (absolute: string, entryPath: string) => {
  const left = absolute.replace(/\\/g, "/").toLowerCase();
  const right = entryPath.replace(/\\/g, "/").toLowerCase();
  return left === right || left.endsWith(`/${right}`);
};

async function run(turn: Turn) {
  if (!plugin || !turn.tool || !turn.args) return;
  const controller = new AbortController();
  running.value = { controller, turn };
  turn.status = "running";
  turn.error = undefined;
  turn.message = "";
  turn.progress = null;
  const started = Date.now();
  try {
    // Plain data: the turn is reactive, the call arguments must not be.
    const args = JSON.parse(JSON.stringify(toRaw(turn.args)));
    const result = await plugin.tools.call(turn.tool, args, {
      signal: controller.signal,
      onProgress: (event: any) => {
        if (turn.status !== "running") return;
        if (event.type === "progress") {
          turn.message = event.message ?? "";
          turn.progress = typeof event.progress === "number" ? event.progress : null;
        } else if (event.type === "partialImage") {
          readBlobUrl(event.path).then((url) => {
            if (turn.status === "running") setPartial(turn, url);
            else URL.revokeObjectURL(url);
          }).catch(() => {});
        }
      },
    });
    if (controller.signal.aborted) {
      turn.status = "cancelled";
    } else if (result.isError) {
      turn.status = "error";
      turn.error = result.text;
    } else {
      const files: string[] = result.files ?? [];
      await loadHistory();
      const recorded = files.length > 0 && files.every((file) => history.value.some((entry) => sameFile(file, entry.path)));
      if (recorded) {
        // The history now has this turn.
        localTurns.value = localTurns.value.filter((item) => item !== turn);
      } else {
        turn.status = "done";
        turn.durationMs = Date.now() - started;
        turn.images = files.map((path, index) => ({ id: `${turn.id}-${index}`, createdAt: turn.createdAt, prompt: turn.prompt, path }));
        turn.text = result.text;
      }
      for (const file of files) void ensureUrl(file);
    }
  } catch (cause) {
    if (controller.signal.aborted) {
      turn.status = "cancelled";
    } else {
      turn.status = "error";
      turn.error = cause instanceof Error ? cause.message : String(cause);
    }
  } finally {
    setPartial(turn, null);
    if (running.value?.controller === controller) running.value = null;
    scrollToBottom();
  }
}

function stop() {
  running.value?.controller.abort();
}

function retry(turn: Turn) {
  if (running.value) return;
  turn.createdAt = new Date().toISOString();
  void run(turn);
}

function dismiss(turn: Turn) {
  localTurns.value = localTurns.value.filter((item) => item !== turn);
}

// ── turn and image actions ──────────────────────────────────────────────

function editImage(entry: HistoryEntry) {
  addReference(entry.path);
  selected.value = null;
  tab.value = "chat";
  void nextTick(() => promptEl.value?.focus());
}

function reuse(turn: Turn) {
  form.prompt = turn.prompt;
  form.references.splice(0, form.references.length, ...turn.references.filter((path) => IMAGE_EXT.test(path)));
  form.mask = turn.mask ?? "";
  if (turn.source !== "codex" && turn.model !== "codex") {
    if (turn.model) {
      form.model = turn.model;
      form.modelMode = "list";
    }
    if (turn.quality) form.quality = turn.quality;
    if (turn.outputFormat) form.outputFormat = turn.outputFormat;
    if (turn.size) applySize(turn.size);
  }
  selected.value = null;
  tab.value = "chat";
  void nextTick(() => promptEl.value?.focus());
}

function entryTurn(entry: HistoryEntry): Turn {
  return turns.value.find((turn) => turn.images.includes(entry))
    ?? { id: entry.id, createdAt: entry.createdAt, prompt: entry.prompt, references: entry.references ?? [], images: [entry], status: "done", model: entry.model, size: entry.size, quality: entry.quality, outputFormat: entry.outputFormat, source: entry.source };
}

function open(entry: HistoryEntry) {
  selected.value = entry;
  copied.value = null;
  void ensureUrl(entry.path);
}

async function copyPath(path: string) {
  try {
    await navigator.clipboard.writeText(path);
    copied.value = path;
    setTimeout(() => {
      if (copied.value === path) copied.value = null;
    }, 1500);
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Escape" && selected.value) selected.value = null;
}

// ── lifecycle ───────────────────────────────────────────────────────────

let releaseSettings: (() => void) | null = null;
let releaseCapabilities: (() => void) | null = null;
let disposed = false;

onMounted(async () => {
  window.addEventListener("keydown", onKeydown);
  if (!plugin) return;
  try {
    await Promise.all([loadSettings(), loadCapabilities()]);
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  }
  for (const path of form.references) void ensureUrl(path);
  if (form.mask) void ensureUrl(form.mask);
  scrollToBottom(true);
  fitPrompt();
  const [release, releaseGrants] = await Promise.all([
    plugin.settings.onChanged(() => { void loadSettings(); }),
    plugin.capabilities.onChanged((list: any[]) => {
      onCodex.value = codexActive(list);
    }),
  ]);
  if (disposed) {
    release();
    releaseGrants();
  } else {
    releaseSettings = release;
    releaseCapabilities = releaseGrants;
  }
});

onBeforeUnmount(() => {
  disposed = true;
  window.removeEventListener("keydown", onKeydown);
  releaseSettings?.();
  releaseCapabilities?.();
  observer?.disconnect();
  running.value?.controller.abort();
  for (const turn of localTurns.value) setPartial(turn, null);
  for (const url of Object.values(urls)) URL.revokeObjectURL(url);
});

watch(() => form.references.length, (length) => {
  if (!length) form.mask = "";
});
</script>

<template>
  <main class="studio">
    <div v-if="!plugin" class="banner warn">{{ tr("notPlugin") }}</div>
    <template v-else>
      <header class="studio-head">
        <BaseSegmented
          v-model="tab"
          class="studio-tabs"
          :options="[{ value: 'chat', label: tr('tabChat') }, { value: 'gallery', label: tr('tabGallery') }]"
          size="sm"
        />
        <span class="mode" :class="{ codex: onCodex }" :title="onCodex ? tr('codexMode') : undefined">
          {{ onCodex ? tr("modeCodex") : tr("modeApi") }}
        </span>
        <span class="head-path" :title="outputDir">{{ outputDir }}</span>
        <BaseButton size="sm" @click="loadHistory()">{{ tr("refresh") }}</BaseButton>
        <BaseButton size="sm" @click="plugin.settings.openSettings()">{{ tr("settings") }}</BaseButton>
      </header>

      <!-- ── chat ─────────────────────────────────────────────────── -->
      <section v-show="tab === 'chat'" ref="threadEl" class="thread" @scroll="onThreadScroll">
        <div class="thread-inner">
          <div v-if="!turns.length" class="empty">
            <div class="empty-title">{{ tr("emptyTitle") }}</div>
            <div class="hint">{{ tr("emptyHint") }}</div>
          </div>
          <div v-if="turns.length > shownTurns" class="earlier">
            <BaseButton size="sm" @click="shownTurns += TURN_PAGE">{{ tr("earlier") }}</BaseButton>
          </div>

          <article v-for="turn in visibleTurns" :key="turn.id" class="turn" :data-turn-status="turn.status">
            <div class="ask">
              <div class="ask-bubble">
                <div v-if="turn.references.length || turn.mask" class="ask-refs">
                  <img
                    v-for="path in turn.references"
                    :key="path"
                    v-lazy="path"
                    :src="urls[path]"
                    class="ask-ref"
                    :title="path"
                    :alt="fileName(path)"
                  >
                  <span v-if="turn.mask" class="tag">{{ tr("mask") }}: {{ fileName(turn.mask) }}</span>
                </div>
                <div class="ask-text">{{ turn.prompt }}</div>
              </div>
            </div>

            <div class="answer">
              <div v-if="turn.caller === 'agent'" class="tag agent">{{ tr("fromAgent") }}</div>

              <template v-if="turn.status === 'running'">
                <div class="result-images single">
                  <div class="placeholder" :class="{ partial: Boolean(turn.partialUrl) }">
                    <img v-if="turn.partialUrl" :src="turn.partialUrl" class="result-image partial" alt="">
                    <span v-else class="spinner" aria-hidden="true" />
                  </div>
                </div>
                <div class="running-line">
                  <span class="progress-text">{{ turn.message || (turn.source === "codex" ? tr("waitingCodex") : tr("waiting")) }}</span>
                  <BaseButton size="sm" @click="stop()">{{ tr("stop") }}</BaseButton>
                </div>
                <div v-if="turn.progress !== null && turn.progress !== undefined" class="progress">
                  <div class="progress-bar" :style="{ width: `${Math.round(turn.progress * 100)}%` }" />
                </div>
              </template>

              <template v-else-if="turn.status === 'error' || turn.status === 'cancelled'">
                <div class="answer-bubble" :class="turn.status">
                  <div v-if="turn.status === 'error'" class="error" role="alert">{{ turn.error }}</div>
                  <div v-else class="hint">{{ tr("cancelled") }}</div>
                  <div class="actions">
                    <BaseButton size="sm" :disabled="Boolean(running)" @click="retry(turn)">{{ tr("retry") }}</BaseButton>
                    <BaseButton size="sm" @click="reuse(turn)">{{ tr("reuse") }}</BaseButton>
                    <BaseButton size="sm" @click="dismiss(turn)">{{ tr("remove") }}</BaseButton>
                  </div>
                </div>
              </template>

              <template v-else>
                <div v-if="turn.images.length" class="result-images" :class="{ single: turn.images.length === 1 }">
                  <button
                    v-for="entry in turn.images"
                    :key="entry.id"
                    v-lazy="entry.path"
                    type="button"
                    class="result"
                    :title="entry.path"
                    @click="open(entry)"
                  >
                    <img v-if="urls[entry.path]" :src="urls[entry.path]" class="result-image" :alt="turn.prompt" @load="scrollToBottom()">
                    <span v-else-if="unreadable[entry.path]" class="hint">{{ tr("unreadable") }}</span>
                    <span v-else class="spinner" aria-hidden="true" />
                  </button>
                </div>
                <div v-if="!turn.images.length && turn.text" class="answer-bubble">{{ turn.text }}</div>
                <div class="meta">{{ turnMeta(turn) }}</div>
                <div v-if="turn.revisedPrompt" class="hint revised"><strong>{{ tr("revised") }}:</strong> {{ turn.revisedPrompt }}</div>
                <div v-if="turn.images.length" class="actions">
                  <BaseButton size="sm" @click="editImage(turn.images[0])">{{ tr("editThis") }}</BaseButton>
                  <BaseButton size="sm" @click="reuse(turn)">{{ tr("reuse") }}</BaseButton>
                  <BaseButton size="sm" @click="copyPath(turn.images[0].path)">
                    {{ copied === turn.images[0].path ? tr("copied") : tr("copyPath") }}
                  </BaseButton>
                </div>
              </template>
            </div>
          </article>
        </div>
      </section>

      <!-- ── gallery ──────────────────────────────────────────────── -->
      <section v-show="tab === 'gallery'" class="gallery">
        <div v-if="!history.length" class="hint empty">
          {{ historyMissing ? tr("galleryMissing", outputDir) : tr("galleryEmpty") }}
        </div>
        <div v-else class="tiles">
          <button
            v-for="entry in visibleTiles"
            :key="entry.id"
            v-lazy="entry.path"
            type="button"
            class="tile"
            :title="entry.prompt"
            @click="open(entry)"
          >
            <img v-if="urls[entry.path]" :src="urls[entry.path]" :alt="entry.prompt">
            <span v-else-if="unreadable[entry.path]" class="hint">{{ tr("unreadable") }}</span>
          </button>
        </div>
        <BaseButton v-if="history.length > shownTiles" size="sm" @click="shownTiles += TILE_PAGE">{{ tr("more") }}</BaseButton>
      </section>

      <!-- ── composer ─────────────────────────────────────────────── -->
      <footer v-show="tab === 'chat'" class="composer-area">
        <div v-if="!onCodex && !keyConfigured" class="banner warn">
          <span>{{ tr("missingKey") }}</span>
          <BaseButton size="sm" @click="plugin.settings.openSettings()">{{ tr("openSettings") }}</BaseButton>
        </div>
        <div v-for="hint in hints" :key="hint" class="hint warn">{{ hint }}</div>
        <div v-if="formError" class="error">{{ formError }}</div>
        <div v-if="error" class="error" role="alert">{{ error }}</div>

        <div ref="composerEl" class="composer" :class="{ active: dragOver }">
          <div v-if="dragOver" class="drop-hint">{{ tr("dropHere") }}</div>
          <div v-if="form.references.length || form.mask" class="refs">
            <div v-for="path in form.references" :key="path" class="ref" :title="path">
              <img v-if="urls[path]" :src="urls[path]" class="ref-thumb" :alt="fileName(path)">
              <span v-else class="ref-thumb ref-name">{{ fileName(path) }}</span>
              <div class="ref-actions">
                <button v-if="isPng(path) && !onCodex" type="button" class="ref-action" @click="useAsMask(path)">{{ tr("useAsMask") }}</button>
                <button type="button" class="ref-action" :aria-label="tr('remove')" :title="tr('remove')" @click="removeReference(path)">×</button>
              </div>
            </div>
            <div v-if="form.mask" class="ref mask" :title="`${tr('maskHint')}\n${form.mask}`">
              <span class="tag">{{ tr("mask") }}: {{ fileName(form.mask) }}</span>
              <button type="button" class="ref-action" :aria-label="tr('remove')" @click="form.mask = ''">×</button>
            </div>
          </div>

          <textarea
            ref="promptEl"
            v-model="form.prompt"
            class="prompt"
            rows="2"
            :placeholder="isEdit ? tr('promptPlaceholderEdit') : tr('promptPlaceholder')"
            @keydown="onPromptKeydown"
          />

          <div class="toolbar">
            <template v-if="onCodex">
              <span class="tag codex" :title="tr('codexMode')">{{ tr("modeCodex") }}</span>
            </template>
            <template v-else>
              <div v-if="form.modelMode === 'custom'" class="model-input">
                <input
                  ref="modelInputEl"
                  v-model="form.model"
                  class="input"
                  spellcheck="false"
                  :placeholder="tr('modelCustomPlaceholder')"
                  :aria-label="tr('model')"
                >
                <button type="button" class="ref-action" :title="tr('modelList')" :aria-label="tr('modelList')" @click="form.modelMode = 'list'">▾</button>
              </div>
              <BaseDropdown
                v-else
                class="opt model"
                :model-value="form.model"
                :options="modelOptions"
                :selected-label="chip('model', modelLabel)"
                :aria-label="tr('model')"
                size="sm"
                menu-align="start"
                teleport
                @update:model-value="chooseModel"
              />
              <BaseDropdown
                class="opt size"
                :model-value="sizeChoice"
                :options="sizeOptions"
                :selected-label="chip('size', sizeLabel)"
                :aria-label="tr('size')"
                size="sm"
                menu-align="start"
                teleport
                @update:model-value="chooseSize"
              />
              <span v-if="form.sizeMode === 'custom'" class="size-input">
                <input
                  class="input num"
                  inputmode="numeric"
                  :value="sizeSide(1)"
                  :aria-label="tr('width')"
                  :placeholder="tr('width')"
                  @input="setSizeSide(1, ($event.target as HTMLInputElement).value)"
                >
                <span>×</span>
                <input
                  class="input num"
                  inputmode="numeric"
                  :value="sizeSide(2)"
                  :aria-label="tr('height')"
                  :placeholder="tr('height')"
                  @input="setSizeSide(2, ($event.target as HTMLInputElement).value)"
                >
              </span>
              <BaseDropdown
                v-model="form.quality"
                class="opt"
                :options="qualityOptions"
                :selected-label="chip('quality', labelOf(qualityOptions, form.quality))"
                :aria-label="tr('quality')"
                size="sm"
                menu-align="start"
                teleport
              />
            </template>
            <BaseDropdown
              v-model="form.background"
              class="opt"
              :options="backgroundOptions"
              :selected-label="chip('background', labelOf(backgroundOptions, form.background))"
              :aria-label="tr('background')"
              size="sm"
              menu-align="start"
              teleport
            />
            <template v-if="!onCodex">
              <BaseDropdown
                v-model="form.outputFormat"
                class="opt"
                :options="formatOptions"
                :selected-label="labelOf(formatOptions, form.outputFormat)"
                :aria-label="tr('format')"
                size="sm"
                menu-align="start"
                teleport
              />
              <BaseDropdown
                v-model="form.n"
                class="opt"
                :options="countOptions"
                :selected-label="labelOf(countOptions, form.n)"
                :aria-label="tr('count')"
                size="sm"
                menu-align="start"
                teleport
              />
            </template>
            <span class="spacer" />
            <button
              v-if="running"
              type="button"
              class="send stop"
              :title="tr('stop')"
              :aria-label="tr('stop')"
              @click="stop()"
            >
              <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true"><rect x="3" y="3" width="10" height="10" rx="1.5" fill="currentColor" /></svg>
            </button>
            <button
              v-else
              type="button"
              class="send"
              :disabled="!canGenerate"
              :title="isEdit ? tr('sendEdit') : tr('send')"
              :aria-label="isEdit ? tr('sendEdit') : tr('send')"
              @click="generate()"
            >
              <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M8 13V3M3.5 7.5 8 3l4.5 4.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" /></svg>
            </button>
          </div>
        </div>
      </footer>

      <!-- ── lightbox ─────────────────────────────────────────────── -->
      <div v-if="selected" class="lightbox" @click.self="selected = null">
        <div class="lightbox-body">
          <img v-if="urls[selected.path]" :src="urls[selected.path]" class="lightbox-image" :alt="selected.prompt">
          <span v-else-if="unreadable[selected.path]" class="hint">{{ tr("unreadable") }}</span>
          <aside class="details">
            <p class="details-prompt">{{ selected.prompt }}</p>
            <p v-if="selected.revisedPrompt" class="hint"><strong>{{ tr("revised") }}:</strong> {{ selected.revisedPrompt }}</p>
            <p class="hint">{{ turnMeta(entryTurn(selected)) }}</p>
            <p v-if="selected.createdAt" class="hint">{{ new Date(selected.createdAt).toLocaleString() }}</p>
            <p v-if="selected.references && selected.references.length" class="hint">
              {{ tr("references_") }}: {{ selected.references.map(fileName).join(", ") }}
            </p>
            <p class="hint path">{{ selected.path }}</p>
            <div class="actions">
              <BaseButton size="sm" @click="editImage(selected)">{{ tr("editThis") }}</BaseButton>
              <BaseButton size="sm" @click="reuse(entryTurn(selected))">{{ tr("reuse") }}</BaseButton>
              <BaseButton size="sm" @click="copyPath(selected.path)">{{ copied === selected.path ? tr("copied") : tr("copyPath") }}</BaseButton>
              <BaseButton size="sm" @click="selected = null">{{ tr("close") }}</BaseButton>
            </div>
          </aside>
        </div>
      </div>
    </template>
  </main>
</template>

<style scoped>
.studio {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  box-sizing: border-box;
  color: var(--text-color);
  font-size: 12px;
  overflow: hidden;
}
.studio-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-color);
}
.mode {
  padding: 1px 8px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  color: var(--text-secondary);
  font-size: 11px;
  white-space: nowrap;
}
.mode.codex {
  border-color: var(--accent-border);
  background: var(--accent-soft);
  color: var(--accent-color);
}
.head-path {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  color: var(--text-tertiary);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* thread */
.thread {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.thread-inner {
  display: flex;
  flex-direction: column;
  gap: 18px;
  max-width: 880px;
  margin: 0 auto;
  padding: 16px 16px 8px;
}
.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 72px 0 24px;
  text-align: center;
}
.empty-title {
  color: var(--text-secondary);
  font-size: 15px;
  font-weight: 600;
}
.earlier {
  display: flex;
  justify-content: center;
}
.turn {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ask {
  display: flex;
  justify-content: flex-end;
}
.ask-bubble {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-width: 75%;
  padding: 8px 12px;
  border-radius: 12px 12px 4px 12px;
  background: var(--accent-soft);
  border: 1px solid var(--accent-border);
}
.ask-text {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  line-height: 1.5;
  font-size: 13px;
}
.ask-refs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}
.ask-ref {
  width: 44px;
  height: 44px;
  border-radius: 4px;
  object-fit: cover;
  background: var(--hover-bg);
}
.answer {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  max-width: 100%;
}
.answer-bubble {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-width: 75%;
  padding: 8px 12px;
  border-radius: 12px 12px 12px 4px;
  border: 1px solid var(--border-color);
  background: var(--surface-elevated, var(--panel-bg));
}
.answer-bubble.error {
  border-color: var(--status-danger-border);
}
.result-images {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 260px));
  gap: 6px;
}
.result-images.single {
  grid-template-columns: minmax(0, 420px);
}
.result,
.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 120px;
  padding: 0;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: repeating-conic-gradient(var(--hover-bg) 0% 25%, transparent 0% 50%) 50% / 16px 16px;
  overflow: hidden;
  cursor: zoom-in;
}
.placeholder {
  width: 260px;
  height: 260px;
  cursor: default;
}
.placeholder.partial {
  width: auto;
  height: auto;
}
.result:hover {
  border-color: var(--accent-border);
}
.result-image {
  display: block;
  max-width: 100%;
  max-height: 420px;
  object-fit: contain;
}
.result-image.partial {
  filter: saturate(0.8) blur(0.4px);
  opacity: 0.85;
}
.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--border-color);
  border-top-color: var(--accent-color);
  border-radius: 50%;
  animation: studio-spin 0.8s linear infinite;
}
@keyframes studio-spin { to { transform: rotate(360deg); } }
.running-line {
  display: flex;
  align-items: center;
  gap: 8px;
}
.progress-text {
  color: var(--text-secondary);
}
.progress {
  width: 260px;
  height: 3px;
  border-radius: 2px;
  background: var(--border-color);
  overflow: hidden;
}
.progress-bar {
  height: 100%;
  background: var(--accent-color);
  transition: width 0.2s ease;
}
.meta {
  color: var(--text-tertiary);
  font-size: 11px;
}
.revised {
  max-width: 75%;
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tag {
  display: inline-flex;
  align-items: center;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--hover-bg);
  color: var(--text-secondary);
  font-size: 11px;
  white-space: nowrap;
}
.tag.agent,
.tag.codex {
  background: var(--accent-soft);
  color: var(--accent-color);
}

/* gallery */
.gallery {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  overflow: auto;
}
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
}
.tile {
  display: flex;
  align-items: center;
  justify-content: center;
  aspect-ratio: 1;
  padding: 0;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--panel-bg);
  overflow: hidden;
  cursor: pointer;
}
.tile:hover {
  border-color: var(--accent-border);
}
.tile img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* composer */
.composer-area {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex-shrink: 0;
  width: 100%;
  max-width: 880px;
  margin: 0 auto;
  padding: 6px 16px 14px;
  box-sizing: border-box;
}
.composer {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 8px 10px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: var(--input-bg);
}
.composer:focus-within {
  border-color: var(--accent-border);
}
.composer.active {
  border-color: var(--accent-color);
  background: var(--accent-soft);
}
.drop-hint {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  color: var(--accent-color);
  font-weight: 600;
  pointer-events: none;
}
.refs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.ref {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}
.ref.mask {
  flex-direction: row;
  align-items: center;
}
.ref-thumb {
  width: 56px;
  height: 56px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  object-fit: cover;
  background: var(--hover-bg);
}
.ref-name {
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  font-size: 10px;
  text-align: center;
  word-break: break-all;
}
.ref-actions {
  display: flex;
  gap: 2px;
}
.ref-action {
  padding: 0 3px;
  border: none;
  background: none;
  color: var(--text-tertiary);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}
.ref-action:hover {
  color: var(--text-color);
}
.prompt {
  width: 100%;
  min-height: 40px;
  max-height: 200px;
  box-sizing: border-box;
  padding: 2px 2px;
  border: none;
  background: transparent;
  color: var(--text-color);
  font: inherit;
  font-size: 13px;
  line-height: 1.5;
  resize: none;
  outline: none;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.opt {
  max-width: 240px;
}
.model-input,
.size-input {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.input {
  height: 24px;
  box-sizing: border-box;
  padding: 0 8px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--panel-bg);
  color: var(--text-color);
  font: inherit;
}
.input:focus {
  outline: none;
  border-color: var(--accent-border);
}
.model-input .input {
  width: 180px;
}
.input.num {
  width: 64px;
  text-align: center;
}
.spacer {
  flex: 1;
}
.send {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: var(--accent-color);
  color: #fff;
  cursor: pointer;
}
.send:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.send.stop {
  background: var(--text-secondary);
}

/* shared */
.banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid var(--border-color);
}
.banner.warn {
  color: var(--status-warn-fg);
  background: var(--status-warn-bg);
  border-color: var(--status-warn-border);
}
.hint {
  color: var(--text-tertiary);
  font-size: 11px;
  line-height: 1.45;
}
.hint.warn {
  color: var(--status-warn-fg);
}
.hint.empty {
  padding: 24px 0;
  text-align: center;
}
.error {
  color: var(--status-danger-fg);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.path {
  overflow-wrap: anywhere;
}

/* lightbox */
.lightbox {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: color-mix(in srgb, var(--bg-color) 80%, transparent);
  z-index: 10;
}
.lightbox-body {
  display: flex;
  gap: 16px;
  max-width: 100%;
  max-height: 100%;
  padding: 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: var(--surface-elevated);
}
.lightbox-image {
  max-width: min(70vw, 1024px);
  max-height: calc(100vh - 120px);
  object-fit: contain;
  border-radius: 4px;
}
.details {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 260px;
  overflow: auto;
}
.details p {
  margin: 0;
}
.details-prompt {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
