<view>
{ "name": "Image Studio", "icon": "image" }
</view>

<script setup lang="ts">
// Image Studio: generate or edit images with the plugin's own tools and
// browse what was saved. Generation runs through view.plugin.tools.call
// (caller "view"), so it streams partial images and shows up in the status
// icon like calls by the model. When the user allowed the Codex subscription
// (Settings → Plugins → OpenAI Image → Permissions) the same tools run on it;
// the form then only offers what the subscription honors. The gallery reads
// history.jsonl in the output folder.
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useLocusFileDropTarget, useViewState, view } from "@locus/view-runtime";
import { BaseButton, BaseDropdown, BaseSegmented } from "@locus/components";

const messages: Record<string, Record<string, string>> = {
  en: {
    notPlugin: "This View belongs to the OpenAI Image plugin and only works when the plugin is enabled for the workspace.",
    missingKey: "The OpenAI API key is not set.",
    openSettings: "Open settings",
    prompt: "Prompt",
    promptPlaceholder: "Describe the image… (Ctrl+Enter to generate)",
    model: "Model",
    size: "Size",
    quality: "Quality",
    background: "Background",
    format: "Format",
    count: "Count",
    references: "Reference images",
    referencesHint: "Drag images here from the file tree to edit or combine them.",
    mask: "Mask",
    maskHint: "Transparent pixels of the mask mark the area of the first image to change.",
    useAsMask: "Use as mask",
    remove: "Remove",
    generate: "Generate",
    edit: "Edit",
    cancel: "Cancel",
    cancelled: "Cancelled.",
    preview: "Preview",
    waiting: "Waiting for the first preview…",
    gallery: "Gallery",
    refresh: "Refresh",
    galleryEmpty: "Generated images appear here.",
    galleryMissing: "No history in {0} yet.",
    more: "Show more",
    copyPath: "Copy path",
    copied: "Copied",
    useAsReference: "Use as reference",
    reusePrompt: "Reuse prompt",
    close: "Close",
    revised: "Revised prompt",
    references_: "References",
    unreadable: "Image not readable",
    codexMode: "Codex subscription: the server picks model, size and quality (currently 1536×1024) and there are no previews. Only the prompt, background and up to 5 references take effect.",
    codexNoMask: "Masks are not available on the Codex subscription.",
    codexTooMany: "The Codex subscription takes at most {0} reference images.",
    waitingCodex: "Waiting for Codex…",
    sourceCodex: "Codex subscription",
    "hint.quality": "{0} quality is only documented for the gpt-image-2.5 models; {1} may reject it.",
    "hint.size": "Custom sizes like {0} are only documented for gpt-image-2 and the 2.5 models; {1} may reject it.",
    "hint.transparent": "Transparent backgrounds are a preview feature on {0}.",
    "size.auto": "Auto",
    "size.1024x1024": "Square 1024×1024",
    "size.1536x1024": "Landscape 1536×1024",
    "size.1024x1536": "Portrait 1024×1536",
    "quality.auto": "Auto",
    "quality.low": "Low",
    "quality.medium": "Medium",
    "quality.high": "High",
    "quality.xhigh": "Extra high",
    "quality.max": "Max",
    "background.auto": "Auto",
    "background.opaque": "Opaque",
    "background.transparent": "Transparent",
    transparentJpeg: "Transparent backgrounds need PNG or WebP.",
  },
  zh: {
    notPlugin: "这个 View 属于 OpenAI Image 插件，需要在工作区启用插件后使用。",
    missingKey: "还没有设置 OpenAI API Key。",
    openSettings: "打开设置",
    prompt: "提示词",
    promptPlaceholder: "描述想要的图片…（Ctrl+Enter 生成）",
    model: "模型",
    size: "尺寸",
    quality: "质量",
    background: "背景",
    format: "格式",
    count: "张数",
    references: "参考图",
    referencesHint: "从文件树把图片拖到这里，即可编辑或合成。",
    mask: "蒙版",
    maskHint: "蒙版中透明的像素表示第一张参考图里要修改的区域。",
    useAsMask: "用作蒙版",
    remove: "移除",
    generate: "生成",
    edit: "编辑",
    cancel: "取消",
    cancelled: "已取消。",
    preview: "预览",
    waiting: "等待第一张预览…",
    gallery: "图库",
    refresh: "刷新",
    galleryEmpty: "生成的图片会显示在这里。",
    galleryMissing: "{0} 中还没有历史记录。",
    more: "显示更多",
    copyPath: "复制路径",
    copied: "已复制",
    useAsReference: "用作参考图",
    reusePrompt: "复用提示词",
    close: "关闭",
    revised: "改写后的提示词",
    references_: "参考图",
    unreadable: "无法读取图片",
    codexMode: "Codex 订阅模式：服务端决定模型、尺寸和质量（目前为 1536×1024），没有中间预览。只有提示词、背景和最多 5 张参考图生效。",
    codexNoMask: "Codex 订阅模式不支持蒙版。",
    codexTooMany: "Codex 订阅模式最多支持 {0} 张参考图。",
    waitingCodex: "等待 Codex 生成…",
    sourceCodex: "Codex 订阅",
    "hint.quality": "{0} 质量只写明了 gpt-image-2.5 系列支持，{1} 可能会拒绝。",
    "hint.size": "{0} 这类自定义尺寸只写明了 gpt-image-2 和 2.5 系列支持，{1} 可能会拒绝。",
    "hint.transparent": "透明背景在 {0} 上还是预览功能。",
    "size.auto": "自动",
    "size.1024x1024": "方形 1024×1024",
    "size.1536x1024": "横向 1536×1024",
    "size.1024x1536": "纵向 1024×1536",
    "quality.auto": "自动",
    "quality.low": "低",
    "quality.medium": "中",
    "quality.high": "高",
    "quality.xhigh": "很高",
    "quality.max": "最高",
    "background.auto": "自动",
    "background.opaque": "不透明",
    "background.transparent": "透明",
    transparentJpeg: "透明背景需要 PNG 或 WebP 格式。",
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
const FIXED_SIZES = ["auto", "1024x1024", "1536x1024", "1024x1536"];
const MIME: Record<string, string> = { png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", webp: "image/webp" };
const PAGE = 24;

// ── form ────────────────────────────────────────────────────────────────

const form = useViewState({
  initialized: false,
  prompt: "",
  model: "",
  size: "auto",
  quality: "auto",
  background: "auto",
  outputFormat: "png",
  n: "1",
  references: [] as string[],
  mask: "",
}, "form");

const settings = ref<Record<string, any>>({});
const keyConfigured = ref(true);
const modelSuggestions = ref<string[]>([]);
/** The user allowed the Codex subscription for this plugin. */
const onCodex = ref(false);

async function loadCapabilities() {
  if (!plugin) return;
  const list = await plugin.capabilities.get();
  onCodex.value = list.some((capability: any) => capability.name === CODEX_IMAGES && capability.granted);
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
    form.size = values.defaultSize ?? "auto";
    form.quality = values.defaultQuality ?? "auto";
    form.background = values.defaultBackground ?? "auto";
    form.outputFormat = values.defaultFormat ?? "png";
    form.initialized = true;
  }
  if (outputChanged) await loadHistory();
}

const sizeOptions = computed(() => {
  const options = FIXED_SIZES.map((value) => ({ value, label: tr(`size.${value}`) }));
  if (form.size && !FIXED_SIZES.includes(form.size)) options.push({ value: form.size, label: form.size });
  return options;
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
const countOptions = ["1", "2", "3", "4"].map((value) => ({ value, label: value }));
const labelOf = (options: { value: string; label: string }[], value: string) =>
  options.find((option) => option.value === value)?.label ?? value;

const isEdit = computed(() => form.references.length > 0);
const formError = computed(() => {
  if (onCodex.value) {
    if (form.mask) return tr("codexNoMask");
    if (form.references.length > MAX_CODEX_REFERENCES) return tr("codexTooMany", MAX_CODEX_REFERENCES);
    return null;
  }
  return form.background === "transparent" && form.outputFormat === "jpeg" ? tr("transparentJpeg") : null;
});

// Combinations a model may reject (same rules as client/hints.ts).
const hints = computed(() => {
  if (onCodex.value) return [];
  const model = form.model.trim().toLowerCase();
  if (!model) return [];
  const is25 = model.startsWith("gpt-image-2.5");
  const is2 = /^gpt-image-2(-\d{4}-\d{2}-\d{2})?$/.test(model);
  const list: string[] = [];
  if ((form.quality === "xhigh" || form.quality === "max") && !is25) list.push(tr("hint.quality", form.quality, model));
  if (form.size && !FIXED_SIZES.includes(form.size) && !is25 && !is2) list.push(tr("hint.size", form.size, model));
  if (form.background === "transparent" && is2) list.push(tr("hint.transparent", model));
  return list;
});
const canGenerate = computed(() =>
  Boolean(plugin) && !running.value && form.prompt.trim().length > 0 && !formError.value);

// ── references ──────────────────────────────────────────────────────────

function addReference(path: string) {
  if (!IMAGE_EXT.test(path) || form.references.includes(path) || form.mask === path) return;
  if (form.references.length >= 16) return;
  form.references.push(path);
}

function removeReference(path: string) {
  form.references.splice(form.references.indexOf(path), 1);
}

function useAsMask(path: string) {
  removeReference(path);
  form.mask = path;
}

// File drops are broadcast to the whole window; only those released over
// the reference area belong here (the chat input does the same).
const refsEl = ref<HTMLElement | null>(null);

function insideRefs(x?: number, y?: number): boolean {
  const bounds = refsEl.value?.getBoundingClientRect();
  if (!bounds || !bounds.width || !Number.isFinite(x) || !Number.isFinite(y)) return false;
  return x! >= bounds.left && x! <= bounds.right && y! >= bounds.top && y! <= bounds.bottom;
}

const drop = useLocusFileDropTarget({
  onDrop: (files: { path: string; isDir: boolean }[], payload: { x?: number; y?: number }) => {
    if (!insideRefs(payload?.x, payload?.y)) return;
    for (const file of files) if (!file.isDir) addReference(file.path);
  },
});
const dragOver = computed(() => {
  const state = drop.dragState.value as { active?: boolean; x?: number; y?: number } | null;
  return Boolean(state?.active) && insideRefs(state?.x, state?.y);
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

// Thumbnails load when they scroll into view.
const observer = typeof IntersectionObserver === "undefined"
  ? null
  : new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      const path = (entry.target as HTMLElement).dataset.path;
      if (path) void ensureUrl(path);
      observer?.unobserve(entry.target);
    }
  }, { rootMargin: "200px" });

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

// ── generation ──────────────────────────────────────────────────────────

interface Running {
  controller: AbortController;
  message: string;
  progress: number | null;
}

const running = ref<Running | null>(null);
const error = ref<string | null>(null);
const notice = ref<string | null>(null);
const partialUrl = ref<string | null>(null);
const resultPaths = ref<string[]>([]);

function setPartial(url: string | null) {
  if (partialUrl.value) URL.revokeObjectURL(partialUrl.value);
  partialUrl.value = url;
}

async function generate() {
  if (!plugin || !canGenerate.value) return;
  const controller = new AbortController();
  running.value = { controller, message: "", progress: null };
  error.value = null;
  notice.value = null;
  resultPaths.value = [];
  setPartial(null);
  // On the subscription only the honored arguments are sent.
  const args: Record<string, unknown> = onCodex.value
    ? { prompt: form.prompt.trim(), background: form.background }
    : {
      prompt: form.prompt.trim(),
      size: form.size,
      quality: form.quality,
      background: form.background,
      outputFormat: form.outputFormat,
      n: Number(form.n),
    };
  if (!onCodex.value && form.model.trim() && form.model.trim() !== settings.value.model) args.model = form.model.trim();
  const tool = isEdit.value ? "image_edit" : "image_generate";
  if (isEdit.value) {
    args.images = [...form.references];
    if (form.mask && !onCodex.value) args.mask = form.mask;
  }
  try {
    const result = await plugin.tools.call(tool, args, {
      signal: controller.signal,
      onProgress: (event: any) => {
        if (!running.value) return;
        if (event.type === "progress") {
          running.value.message = event.message ?? "";
          running.value.progress = typeof event.progress === "number" ? event.progress : null;
        } else if (event.type === "partialImage") {
          readBlobUrl(event.path).then((url) => {
            if (running.value?.controller === controller) setPartial(url);
            else URL.revokeObjectURL(url);
          }).catch(() => {});
        }
      },
    });
    if (controller.signal.aborted) {
      notice.value = tr("cancelled");
    } else if (result.isError) {
      error.value = result.text;
    } else {
      resultPaths.value = result.files;
      setPartial(null);
      await Promise.all(result.files.map((path: string) => ensureUrl(path)));
      await loadHistory();
    }
  } catch (cause) {
    if (controller.signal.aborted) notice.value = tr("cancelled");
    else error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    if (running.value?.controller === controller) running.value = null;
  }
}

function cancel() {
  running.value?.controller.abort();
}

function onPromptKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    void generate();
  }
}

// ── gallery ─────────────────────────────────────────────────────────────

interface HistoryEntry {
  id: string;
  createdAt: string;
  tool: string;
  prompt: string;
  revisedPrompt?: string | null;
  model: string;
  size: string;
  quality: string;
  background?: string;
  outputFormat: string;
  path: string;
  references?: string[];
  /** `codex` (Codex subscription) or `apiKey`; absent in entries of 0.1. */
  source?: string;
}

const history = ref<HistoryEntry[]>([]);
const historyMissing = ref(false);
const shown = ref(PAGE);
const selected = ref<HistoryEntry | null>(null);
const copied = ref(false);

const outputDir = computed(() => String(settings.value.outputDir || "Locus/generated/images"));
const visibleHistory = computed(() => history.value.slice(0, shown.value));

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
    history.value = entries.reverse();
    historyMissing.value = false;
  } catch {
    history.value = [];
    historyMissing.value = true;
  }
}

function open(entry: HistoryEntry) {
  selected.value = entry;
  copied.value = false;
  void ensureUrl(entry.path);
}

async function copyPath(path: string) {
  try {
    await navigator.clipboard.writeText(path);
    copied.value = true;
    setTimeout(() => { copied.value = false; }, 1500);
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  }
}

function reuse(entry: HistoryEntry) {
  form.prompt = entry.prompt;
  if (entry.source === "codex") {
    selected.value = null;
    return;
  }
  if (entry.model) form.model = entry.model;
  if (entry.quality) form.quality = entry.quality;
  if (entry.outputFormat) form.outputFormat = entry.outputFormat;
  if (entry.size && entry.size !== "auto") form.size = entry.size;
  selected.value = null;
}

function useAsReference(entry: HistoryEntry) {
  addReference(entry.path);
  selected.value = null;
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
  const [release, releaseGrants] = await Promise.all([
    plugin.settings.onChanged(() => { void loadSettings(); }),
    plugin.capabilities.onChanged((list: any[]) => {
      onCodex.value = list.some((capability) => capability.name === CODEX_IMAGES && capability.granted);
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
  setPartial(null);
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
      <section class="compose">
        <div v-if="onCodex" class="banner info">{{ tr("codexMode") }}</div>
        <div v-else-if="!keyConfigured" class="banner warn">
          <span>{{ tr("missingKey") }}</span>
          <BaseButton size="sm" @click="plugin.settings.openSettings()">{{ tr("openSettings") }}</BaseButton>
        </div>

        <label class="field">
          <span class="label">{{ tr("prompt") }}</span>
          <textarea
            v-model="form.prompt"
            class="prompt"
            rows="6"
            :placeholder="tr('promptPlaceholder')"
            @keydown="onPromptKeydown"
          />
        </label>

        <div class="grid">
          <label v-if="!onCodex" class="field">
            <span class="label">{{ tr("model") }}</span>
            <input v-model="form.model" class="input" list="image-studio-models" spellcheck="false">
            <datalist id="image-studio-models">
              <option v-for="name in modelSuggestions" :key="name" :value="name" />
            </datalist>
          </label>
          <div v-if="!onCodex" class="field">
            <span class="label">{{ tr("size") }}</span>
            <BaseDropdown v-model="form.size" :options="sizeOptions" :selected-label="labelOf(sizeOptions, form.size)" size="sm" teleport />
          </div>
          <div v-if="!onCodex" class="field">
            <span class="label">{{ tr("quality") }}</span>
            <BaseDropdown v-model="form.quality" :options="qualityOptions" :selected-label="labelOf(qualityOptions, form.quality)" size="sm" teleport />
          </div>
          <div class="field">
            <span class="label">{{ tr("background") }}</span>
            <BaseDropdown v-model="form.background" :options="backgroundOptions" :selected-label="labelOf(backgroundOptions, form.background)" size="sm" teleport />
          </div>
          <div v-if="!onCodex" class="field">
            <span class="label">{{ tr("format") }}</span>
            <BaseSegmented v-model="form.outputFormat" :options="formatOptions" size="sm" />
          </div>
          <div v-if="!onCodex" class="field">
            <span class="label">{{ tr("count") }}</span>
            <BaseSegmented v-model="form.n" :options="countOptions" size="sm" />
          </div>
        </div>

        <div class="field">
          <span class="label">{{ tr("references") }}</span>
          <div ref="refsEl" class="refs" :class="{ active: dragOver }">
            <span v-if="!form.references.length && !form.mask" class="hint">{{ tr("referencesHint") }}</span>
            <div v-for="path in form.references" :key="path" class="chip" :title="path">
              <span class="chip-name">{{ fileName(path) }}</span>
              <button v-if="isPng(path) && !onCodex" type="button" class="chip-action" @click="useAsMask(path)">{{ tr("useAsMask") }}</button>
              <button type="button" class="chip-action" :aria-label="tr('remove')" @click="removeReference(path)">×</button>
            </div>
            <div v-if="form.mask" class="chip mask" :title="`${tr('maskHint')}\n${form.mask}`">
              <span class="chip-name">{{ tr("mask") }}: {{ fileName(form.mask) }}</span>
              <button type="button" class="chip-action" :aria-label="tr('remove')" @click="form.mask = ''">×</button>
            </div>
          </div>
        </div>

        <div v-if="formError" class="error">{{ formError }}</div>
        <div v-for="hint in hints" :key="hint" class="hint warn">{{ hint }}</div>

        <div class="actions">
          <BaseButton variant="primary" :disabled="!canGenerate" @click="generate()">
            {{ isEdit ? tr("edit") : tr("generate") }}
          </BaseButton>
          <BaseButton v-if="running" @click="cancel()">{{ tr("cancel") }}</BaseButton>
          <span v-if="running" class="progress-text">{{ running.message || (onCodex ? tr("waitingCodex") : tr("waiting")) }}</span>
        </div>
        <div v-if="running && running.progress !== null" class="progress">
          <div class="progress-bar" :style="{ width: `${Math.round(running.progress * 100)}%` }" />
        </div>

        <div v-if="error" class="error" role="alert">{{ error }}</div>
        <div v-if="notice" class="hint">{{ notice }}</div>

        <div v-if="partialUrl || resultPaths.length" class="preview">
          <span class="label">{{ tr("preview") }}</span>
          <div class="preview-images">
            <img v-if="partialUrl && running" :src="partialUrl" class="preview-image partial" alt="">
            <template v-else>
              <img v-for="path in resultPaths" :key="path" :src="urls[path]" class="preview-image" :alt="fileName(path)">
            </template>
          </div>
        </div>
      </section>

      <section class="gallery">
        <header class="gallery-head">
          <span class="label">{{ tr("gallery") }}</span>
          <span class="hint path">{{ outputDir }}</span>
          <BaseButton size="sm" @click="loadHistory()">{{ tr("refresh") }}</BaseButton>
        </header>
        <div v-if="!history.length" class="hint empty">
          {{ historyMissing ? tr("galleryMissing", outputDir) : tr("galleryEmpty") }}
        </div>
        <div v-else class="tiles">
          <button
            v-for="entry in visibleHistory"
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
        <BaseButton v-if="history.length > shown" size="sm" @click="shown += PAGE">{{ tr("more") }}</BaseButton>
      </section>

      <div v-if="selected" class="lightbox" @click.self="selected = null">
        <div class="lightbox-body">
          <img v-if="urls[selected.path]" :src="urls[selected.path]" class="lightbox-image" :alt="selected.prompt">
          <span v-else-if="unreadable[selected.path]" class="hint">{{ tr("unreadable") }}</span>
          <aside class="details">
            <p class="details-prompt">{{ selected.prompt }}</p>
            <p v-if="selected.revisedPrompt" class="hint"><strong>{{ tr("revised") }}:</strong> {{ selected.revisedPrompt }}</p>
            <p class="hint">
              {{ selected.source === "codex" ? tr("sourceCodex") : selected.model }} · {{ selected.size }} · {{ selected.quality }} · {{ selected.outputFormat }}
            </p>
            <p class="hint">{{ new Date(selected.createdAt).toLocaleString() }}</p>
            <p v-if="selected.references && selected.references.length" class="hint">
              {{ tr("references_") }}: {{ selected.references.map(fileName).join(", ") }}
            </p>
            <p class="hint path">{{ selected.path }}</p>
            <div class="details-actions">
              <BaseButton size="sm" @click="copyPath(selected.path)">{{ copied ? tr("copied") : tr("copyPath") }}</BaseButton>
              <BaseButton size="sm" @click="useAsReference(selected)">{{ tr("useAsReference") }}</BaseButton>
              <BaseButton size="sm" @click="reuse(selected)">{{ tr("reusePrompt") }}</BaseButton>
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
  display: grid;
  grid-template-columns: minmax(300px, 380px) 1fr;
  gap: 12px;
  height: 100%;
  padding: 12px;
  box-sizing: border-box;
  color: var(--text-color);
  font-size: 12px;
  overflow: hidden;
}
.compose,
.gallery {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  overflow: auto;
}
.banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid var(--border-color);
}
.banner.warn {
  color: var(--status-warn-fg);
  background: var(--status-warn-bg);
  border-color: var(--status-warn-border);
}
.banner.info {
  color: var(--text-secondary);
  background: var(--accent-soft);
  border-color: var(--accent-border);
  line-height: 1.45;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
}
.hint {
  color: var(--text-tertiary);
  font-size: 11px;
}
.hint.warn {
  color: var(--status-warn-fg);
  line-height: 1.4;
}
.path {
  overflow-wrap: anywhere;
}
.prompt,
.input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--input-bg);
  color: var(--text-color);
  font: inherit;
}
.prompt {
  padding: 8px;
  resize: vertical;
  min-height: 96px;
}
.input {
  height: 26px;
  padding: 0 8px;
}
.prompt:focus,
.input:focus {
  outline: none;
  border-color: var(--accent-border);
}
.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 10px;
}
.refs {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  min-height: 34px;
  padding: 6px;
  border: 1px dashed var(--border-color);
  border-radius: 6px;
}
.refs.active {
  border-color: var(--accent-color);
  background: var(--accent-soft);
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  padding: 2px 4px 2px 8px;
  border-radius: 10px;
  background: var(--hover-bg);
}
.chip.mask {
  background: var(--accent-soft);
}
.chip-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chip-action {
  border: none;
  background: none;
  color: var(--text-tertiary);
  font-size: 11px;
  cursor: pointer;
}
.chip-action:hover {
  color: var(--text-color);
}
.actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.progress-text {
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.progress {
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
.error {
  color: var(--status-danger-fg);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.preview-images {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.preview-image {
  max-width: 100%;
  max-height: 320px;
  border-radius: 6px;
  border: 1px solid var(--border-color);
  object-fit: contain;
  background: repeating-conic-gradient(var(--hover-bg) 0% 25%, transparent 0% 50%) 50% / 16px 16px;
}
.preview-image.partial {
  filter: saturate(0.8);
  opacity: 0.85;
}
.gallery-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gallery-head .path {
  flex: 1;
  min-width: 0;
}
.empty {
  padding: 24px 0;
  text-align: center;
}
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
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
.details-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}
</style>
