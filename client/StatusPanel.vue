<script setup lang="ts">
// Popover of the image status icon. Everything arrives through props
// injected by index.ts; the component never sees the plugin context.
import { computed, ref } from "vue";
import { PluginSecretField } from "@locus/plugin-runtime";
import { BaseButton, BaseCheckbox, BaseDropdown } from "@locus/components";
import { modelHints } from "./hints";

const props = defineProps({
  t: { type: Function, required: true },
  activity: { type: Object, required: true },
  apiKey: { type: Object, required: true },
  codex: { type: Object, required: true },
  settings: { type: Object, required: true },
  settingInfo: { type: Function, required: true },
  openStudio: { type: Function, required: true },
  openSettings: { type: Function, required: true },
  disableInWorkspace: { type: Function, required: true },
});

const t = (key: string, ...args: unknown[]) => props.t(key, ...args) as string;
const current = computed(() => (props.activity as any).value);
const keyConfigured = computed(() => Boolean((props.apiKey as any).value?.configured));
/** The user allowed the Codex subscription (Plugins → OpenAI Image → Settings). */
const onCodex = computed(() => Boolean((props.codex as any).value));
const settings = props.settings as Record<string, any>;
const error = ref<string | null>(null);
const busy = ref(false);

const sizeOptions = computed(() => [
  { value: "auto", label: t("size.auto") },
  { value: "1024x1024", label: t("size.square") },
  { value: "1536x1024", label: t("size.landscape") },
  { value: "1024x1536", label: t("size.portrait") },
]);
const qualityOptions = computed(() =>
  ["auto", "low", "medium", "high", "xhigh", "max"].map((value) => ({ value, label: t(`quality.${value}`) })));
const modelSuggestions = computed<string[]>(() => (props.settingInfo as any)("model")?.kind?.suggestions ?? []);
const hints = computed(() => modelHints({
  model: settings.model,
  size: settings.defaultSize,
  quality: settings.defaultQuality,
  background: settings.defaultBackground,
}).map((hint) => t(hint.key, ...hint.args)));
const sizeLabel = computed(() =>
  sizeOptions.value.find((option) => option.value === settings.defaultSize)?.label ?? String(settings.defaultSize ?? ""));

const model = computed({
  get: () => String(settings.model ?? ""),
  set: (value: string) => {
    const trimmed = value.trim();
    if (trimmed && trimmed !== settings.model) settings.model = trimmed;
  },
});

function commitModel(event: Event) {
  model.value = (event.target as HTMLInputElement).value;
}

function hideIcon() {
  settings.showStatusIcon = false;
}

function ago(ms: number): string {
  const minutes = Math.floor((Date.now() - ms) / 60000);
  if (minutes < 1) return t("panel.ago.now");
  if (minutes < 60) return t("panel.ago.minutes", minutes);
  return t("panel.ago.hours", Math.floor(minutes / 60));
}

async function run(action: () => unknown) {
  if (busy.value) return;
  busy.value = true;
  error.value = null;
  try {
    await action();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="oi-panel">
    <section v-if="current.running" class="oi-section">
      <div class="oi-label">{{ t("panel.running") }}</div>
      <div v-for="call in current.calls" :key="call.callId" class="oi-call">
        <span class="oi-call-tool">{{ call.tool }}</span>
        <span class="oi-muted">{{ call.message || t("status.generating") }}</span>
        <div v-if="typeof call.progress === 'number'" class="oi-progress">
          <div class="oi-progress-bar" :style="{ width: `${Math.round(call.progress * 100)}%` }" />
        </div>
      </div>
    </section>

    <section class="oi-section">
      <div class="oi-label">{{ t("panel.last") }}</div>
      <div v-if="current.last" class="oi-last" :class="{ error: current.last.isError }">
        <div class="oi-last-summary">{{ current.last.summary }}</div>
        <div class="oi-muted">
          {{ current.last.tool }} · {{ t(`panel.caller.${current.last.caller}`) }} ·
          {{ t("panel.duration", (current.last.durationMs / 1000).toFixed(1)) }} · {{ ago(current.last.finishedAtMs) }}
        </div>
      </div>
      <div v-else class="oi-muted">{{ t("panel.lastNone") }}</div>
    </section>

    <section class="oi-section">
      <div class="oi-row">
        <span class="oi-label">{{ t("mode.label") }}</span>
        <span class="oi-mode" :class="{ codex: onCodex }" :title="t('mode.switchHint')">
          {{ onCodex ? t("mode.codex") : t("mode.apiKey") }}
        </span>
      </div>
      <div v-if="onCodex" class="oi-muted">{{ t("mode.codexNote") }}</div>
    </section>

    <section class="oi-section">
      <div class="oi-label">{{ t("panel.quick") }}</div>
      <label v-if="!onCodex" class="oi-row">
        <span>{{ t("panel.model") }}</span>
        <input
          class="oi-input"
          list="openai-image-models"
          :value="model"
          spellcheck="false"
          @change="commitModel"
          @keydown.enter="commitModel"
        >
        <datalist id="openai-image-models">
          <option v-for="name in modelSuggestions" :key="name" :value="name" />
        </datalist>
      </label>
      <div v-if="!onCodex" class="oi-row">
        <span>{{ t("panel.size") }}</span>
        <BaseDropdown
          :model-value="String(settings.defaultSize ?? 'auto')"
          :options="sizeOptions"
          :selected-label="sizeLabel"
          size="sm"
          menu-align="end"
          teleport
          @update:model-value="settings.defaultSize = $event"
        />
      </div>
      <div v-if="!onCodex" class="oi-row">
        <span>{{ t("panel.quality") }}</span>
        <BaseDropdown
          :model-value="String(settings.defaultQuality ?? 'auto')"
          :options="qualityOptions"
          size="sm"
          menu-align="end"
          teleport
          @update:model-value="settings.defaultQuality = $event"
        />
      </div>
      <div v-for="hint in onCodex ? [] : hints" :key="hint" class="oi-hint">{{ hint }}</div>
      <label class="oi-row">
        <span>{{ t("panel.attach") }}</span>
        <BaseCheckbox
          :model-value="settings.attachToModel !== false"
          :aria-label="t('panel.attach')"
          @update:model-value="settings.attachToModel = $event"
        />
      </label>
    </section>

    <section v-if="!onCodex" class="oi-section">
      <div class="oi-label" :class="{ warn: !keyConfigured }">{{ t("panel.apiKey") }}</div>
      <PluginSecretField name="apiKey" />
    </section>

    <div v-if="error" class="oi-error" role="alert">{{ error }}</div>

    <div class="oi-actions">
      <BaseButton size="sm" variant="primary" :disabled="busy" @click="run(() => openStudio())">
        {{ t("panel.openStudio") }}
      </BaseButton>
      <BaseButton size="sm" :disabled="busy" @click="run(() => openSettings())">{{ t("panel.settings") }}</BaseButton>
    </div>
    <div class="oi-actions secondary">
      <button type="button" class="oi-link" :title="t('panel.hideHint')" :disabled="busy" @click="hideIcon">
        {{ t("panel.hide") }}
      </button>
      <button type="button" class="oi-link" :disabled="busy" @click="run(() => disableInWorkspace())">
        {{ t("panel.disable") }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.oi-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 300px;
  font-size: 12px;
  color: var(--text-color);
}
.oi-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.oi-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
}
.oi-label.warn {
  color: var(--status-warn-fg);
}
.oi-mode {
  padding: 1px 6px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  color: var(--text-secondary);
  font-size: 11px;
}
.oi-mode.codex {
  border-color: var(--accent-border);
  color: var(--accent-color);
}
.oi-hint {
  color: var(--status-warn-fg);
  font-size: 11px;
  line-height: 1.4;
}
.oi-muted {
  color: var(--text-tertiary);
  font-size: 11px;
}
.oi-call {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 6px;
}
.oi-call-tool {
  font-family: var(--font-mono, monospace);
  font-size: 11px;
}
.oi-progress {
  flex-basis: 100%;
  height: 3px;
  border-radius: 2px;
  background: var(--border-color);
  overflow: hidden;
}
.oi-progress-bar {
  height: 100%;
  background: var(--accent-color);
  transition: width 0.2s ease;
}
.oi-last {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.oi-last-summary {
  overflow-wrap: anywhere;
}
.oi-last.error .oi-last-summary {
  color: var(--status-warn-fg);
}
.oi-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 24px;
}
.oi-input {
  width: 170px;
  height: 24px;
  padding: 0 6px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  background: var(--input-bg);
  color: var(--text-color);
  font-size: 12px;
}
.oi-input:focus {
  outline: none;
  border-color: var(--accent-border);
}
.oi-error {
  color: var(--status-danger-fg);
  overflow-wrap: anywhere;
}
.oi-actions {
  display: flex;
  gap: 6px;
}
.oi-actions.secondary {
  justify-content: space-between;
}
.oi-link {
  padding: 0;
  border: none;
  background: none;
  color: var(--text-tertiary);
  font-size: 11px;
  cursor: pointer;
}
.oi-link:hover:not(:disabled) {
  color: var(--text-color);
  text-decoration: underline;
}
</style>
