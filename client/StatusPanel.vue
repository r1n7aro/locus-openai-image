<script setup lang="ts">
// Popover of the image status icon, built from the same parts as the
// built-in status popovers: the image source as a segmented choice, then a
// grid of secondary labels and controls, then actions. Everything arrives
// through props injected by index.ts; the component never sees the plugin
// context. The source switch is Locus's own `PluginCapabilityField`: only the
// user's click grants the Codex subscription.
import { computed, ref } from "vue";
// `PluginCapabilityField` is undefined on hosts older than it: the source is
// then shown read only (switch it on the Settings tab).
import { PluginCapabilityField, PluginSecretField } from "@locus/plugin-runtime";
import { BaseButton, BaseDropdown, BaseSwitch } from "@locus/components";
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
/** Granted and usable (a grant needs a Codex sign-in). */
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
const hints = computed(() => (onCodex.value ? [] : modelHints({
  model: settings.model,
  size: settings.defaultSize,
  quality: settings.defaultQuality,
  background: settings.defaultBackground,
}).map((hint) => t(hint.key, ...hint.args))));
const sizeLabel = computed(() =>
  sizeOptions.value.find((option) => option.value === settings.defaultSize)?.label ?? String(settings.defaultSize ?? ""));

/** First line of the tool result without the colon that leads into the paths. */
const lastSummary = computed(() => String(current.value.last?.summary ?? "").replace(/[:：]\s*$/, ""));

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
    <component :is="PluginCapabilityField" v-if="PluginCapabilityField" name="codex.images" />
    <div v-else class="oi-grid">
      <span class="oi-key">{{ t("mode.label") }}</span>
      <span :title="t('mode.switchHint')">{{ onCodex ? t("mode.codex") : t("mode.apiKey") }}</span>
    </div>
    <p v-if="onCodex" class="oi-note">{{ t("mode.codexNote") }}</p>

    <div class="oi-grid">
      <template v-if="!onCodex">
        <label class="oi-key" for="openai-image-model">{{ t("panel.model") }}</label>
        <input
          id="openai-image-model"
          class="oi-input"
          list="openai-image-models"
          :value="model"
          spellcheck="false"
          autocomplete="off"
          @change="commitModel"
          @keydown.enter="commitModel"
        >
        <datalist id="openai-image-models">
          <option v-for="name in modelSuggestions" :key="name" :value="name" />
        </datalist>
        <span class="oi-key">{{ t("panel.size") }}</span>
        <BaseDropdown
          :model-value="String(settings.defaultSize ?? 'auto')"
          :options="sizeOptions"
          :selected-label="sizeLabel"
          :aria-label="t('panel.size')"
          size="sm"
          menu-align="end"
          teleport
          @update:model-value="settings.defaultSize = $event"
        />
        <span class="oi-key">{{ t("panel.quality") }}</span>
        <BaseDropdown
          :model-value="String(settings.defaultQuality ?? 'auto')"
          :options="qualityOptions"
          :aria-label="t('panel.quality')"
          size="sm"
          menu-align="end"
          teleport
          @update:model-value="settings.defaultQuality = $event"
        />
        <p v-for="hint in hints" :key="hint" class="oi-hint">{{ hint }}</p>
        <span class="oi-key" :class="{ warn: !keyConfigured }">{{ t("panel.apiKey") }}</span>
        <PluginSecretField name="apiKey" />
      </template>
      <span class="oi-key" :title="t('panel.attachHint')">{{ t("panel.attach") }}</span>
      <BaseSwitch
        class="oi-switch"
        :model-value="settings.attachToModel !== false"
        :aria-label="t('panel.attachHint')"
        @update:model-value="settings.attachToModel = $event"
      />
      <template v-if="current.running">
        <span class="oi-key oi-top">{{ t("panel.running") }}</span>
        <div class="oi-value">
          <div v-for="call in current.calls" :key="call.callId" class="oi-call">
            <span>{{ call.message || t("status.generating") }}</span>
            <div v-if="typeof call.progress === 'number'" class="oi-progress">
              <div class="oi-progress-bar" :style="{ width: `${Math.round(call.progress * 100)}%` }" />
            </div>
          </div>
        </div>
      </template>
      <span class="oi-key oi-top">{{ t("panel.last") }}</span>
      <div v-if="current.last" class="oi-value" :class="{ 'is-error': current.last.isError }">
        <div class="oi-last-summary">{{ lastSummary }}</div>
        <div class="oi-meta">
          {{ current.last.tool }} · {{ t(`panel.caller.${current.last.caller}`) }} ·
          {{ t("panel.duration", (current.last.durationMs / 1000).toFixed(1)) }} · {{ ago(current.last.finishedAtMs) }}
        </div>
      </div>
      <div v-else class="oi-value oi-meta">{{ t("panel.lastNone") }}</div>
    </div>

    <p v-if="error" class="oi-error" role="alert">{{ error }}</p>

    <div class="oi-actions">
      <BaseButton size="sm" variant="primary" :disabled="busy" @click="run(() => openStudio())">
        {{ t("panel.openStudio") }}
      </BaseButton>
      <BaseButton size="sm" :disabled="busy" @click="run(() => openSettings())">{{ t("panel.settings") }}</BaseButton>
    </div>
    <div class="oi-footer">
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
/* Sizes and colors of the built-in status popovers. */
.oi-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-size: 12px;
  color: var(--text-color);
}
.oi-grid {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  align-items: center;
  gap: 6px 10px;
}
.oi-key {
  color: var(--text-secondary);
}
.oi-key.warn {
  color: var(--status-warn-fg);
}
.oi-note,
.oi-hint,
.oi-error {
  margin: 0;
  font-size: 11px;
  line-height: 1.45;
}
.oi-note {
  margin-top: -4px;
  color: var(--text-secondary);
}
.oi-hint {
  grid-column: 1 / -1;
  color: var(--status-warn-fg);
}
.oi-error {
  color: var(--status-danger-fg);
  overflow-wrap: anywhere;
}
.oi-input {
  min-width: 0;
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--input-bg);
  color: var(--text-color);
  font-family: inherit;
  font-size: 12px;
  outline: none;
  box-sizing: border-box;
  transition: border-color 0.15s ease;
}
.oi-input:focus {
  border-color: var(--accent-border);
}
.oi-switch {
  justify-self: end;
}
/* Labels of multi-line values sit on their first line. */
.oi-top {
  align-self: start;
  line-height: 1.45;
}
.oi-value {
  min-width: 0;
  line-height: 1.45;
  overflow-wrap: anywhere;
}
.oi-value.is-error .oi-last-summary {
  color: var(--status-danger-fg);
}
.oi-meta {
  color: var(--text-secondary);
  font-size: 11px;
}
.oi-last-summary + .oi-meta {
  margin-top: 2px;
}
.oi-call + .oi-call {
  margin-top: 4px;
}
.oi-progress {
  height: 3px;
  margin-top: 4px;
  border-radius: 2px;
  background: var(--border-color);
  overflow: hidden;
}
.oi-progress-bar {
  height: 100%;
  background: var(--accent-color);
  transition: width 0.2s ease;
}
.oi-actions {
  display: flex;
  gap: 6px;
}
.oi-footer {
  display: flex;
  justify-content: space-between;
  margin-top: -4px;
}
.oi-link {
  padding: 0;
  border: none;
  background: none;
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
}
.oi-link:hover:not(:disabled) {
  color: var(--text-color);
  text-decoration: underline;
}
</style>
