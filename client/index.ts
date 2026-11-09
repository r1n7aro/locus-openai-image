// Client entry of openai-image: the image status icon of the chat input.
// The icon reflects the plugin's tool activity in this workspace (calls by
// the model and by Image Studio alike), the image source and whether it is
// set up; its colors follow the built-in icons (green usable, gray not set
// up, accent while generating, red after a failure). The popover switches
// the source (the `imageSource` setting, which plugin code may write; the
// `codex.images` permission itself is only granted on the Settings tab) and
// holds the common defaults.
import { computed } from "vue";
import { defineStatusItem } from "@locus/plugin-runtime";
import StatusPanel from "./StatusPanel.vue";
import { messages } from "./locales";
import { CODEX_IMAGES, usesCodex } from "./tools";

const QUICK_SETTINGS = ["imageSource", "model", "defaultSize", "defaultQuality", "defaultBackground", "attachToModel"];

export function apply(ctx: any) {
  const t = ctx.locale.register(messages);
  const activity = ctx.tools.activity();
  const apiKey = ctx.settings.secret("apiKey");
  const settings = ctx.settings.bind(QUICK_SETTINGS);
  /** `available`: signed in to Codex; `granted`: the permission, and usable. */
  const codexPermission = computed(() => {
    const state = (ctx.capabilities.list ?? []).find((item: any) => item.name === CODEX_IMAGES);
    return { available: Boolean(state) && state.available !== false, granted: ctx.capabilities.granted(CODEX_IMAGES) };
  });
  /** The source tool calls use now. */
  const codex = computed(() => usesCodex(settings.imageSource, codexPermission.value.granted));

  ctx.slots.register(
    { slot: "chat.input.status", id: "image" },
    defineStatusItem({
      state: () => computed(() => {
        const current = activity.value;
        if (current.running) return { tone: "accent", busy: true, summary: t("status.generating") };
        if (!codex.value && !apiKey.value.configured) return { tone: "muted", summary: t("status.missingKey") };
        if (current.lastError) return { tone: "danger", summary: t("status.failed") };
        return { tone: "success", summary: t(codex.value ? "status.readyCodex" : "status.readyApiKey") };
      }),
      panel: StatusPanel,
      inject: () => ({
        t,
        activity,
        apiKey,
        codex,
        codexPermission,
        settings,
        settingInfo: (name: string) => ctx.settings.state?.settings.find((item: any) => item.name === name) ?? null,
        openStudio: () => ctx.views.open("image-studio"),
        openSettings: () => ctx.openSettings(),
      }),
    }),
  );
}
