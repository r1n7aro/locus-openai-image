// Client entry of openai-image: the image status icon of the chat input.
// The icon reflects the plugin's tool activity in this workspace (calls by
// the model and by Image Studio alike), the generation mode (Codex
// subscription when the user allowed it, otherwise the API key) and whether
// the API key is set; its popover holds the common defaults and shortcuts.
import { computed } from "vue";
import { defineStatusItem } from "@locus/plugin-runtime";
import StatusPanel from "./StatusPanel.vue";
import { messages } from "./locales";

const QUICK_SETTINGS = ["model", "defaultSize", "defaultQuality", "defaultBackground", "attachToModel", "showStatusIcon"];

export function apply(ctx: any) {
  const t = ctx.locale.register(messages);
  const activity = ctx.tools.activity();
  const apiKey = ctx.settings.secret("apiKey");
  const codex = computed(() => ctx.capabilities.granted("codex.images"));

  ctx.slots.register(
    { slot: "chat.input.status", id: "image" },
    defineStatusItem({
      state: () => computed(() => {
        const current = activity.value;
        if (current.running) {
          return { tone: "accent", busy: true, summary: current.message ?? t("status.generating") };
        }
        if (!codex.value && !apiKey.value.configured) return { tone: "warning", summary: t("status.missingKey") };
        if (current.lastError) return { tone: "warning", summary: current.lastError };
        return { tone: "neutral", summary: t(codex.value ? "status.idleCodex" : "status.idle") };
      }),
      panel: StatusPanel,
      inject: () => ({
        t,
        activity,
        apiKey,
        codex,
        settings: ctx.settings.bind(QUICK_SETTINGS),
        settingInfo: (name: string) => ctx.settings.state?.settings.find((item: any) => item.name === name) ?? null,
        openStudio: () => ctx.views.open("image-studio"),
        openSettings: () => ctx.openSettings(),
        disableInWorkspace: () => ctx.workspace.setPluginEnabled(false),
      }),
    }),
  );
}
