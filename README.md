# OpenAI Image for Locus

[中文](README.zh.md)

Generate and edit images with the OpenAI Images API from Locus: the model gets two tools, the chat input gets a status icon, and the **Image Studio** View lets you generate images directly. Images can be paid with your own OpenAI API key or, if you allow it, with the image quota of your ChatGPT subscription through Codex.

## Features

- **Tools for the model**
  - `image_generate`: text-to-image. Parameters: prompt, size, quality, background, outputFormat, n (1–4), fileName, model.
  - `image_edit`: edit or combine workspace images, with an optional PNG mask.
  - Images are saved to the output folder (default `Locus/generated/images`), and each one is recorded in `history.jsonl` in that folder.
  - The tool result lists the saved paths, the revised prompt and token usage. When "Show generated images to the model" is on, the images are attached too.
- **Status icon** in the chat input
  - Shows whether a generation is running (by the model or in Image Studio), whether the API key is missing, and the last error.
  - The popover has the common defaults, the API key field, the last result, and shortcuts to Image Studio, the full settings, hiding the icon, and disabling the plugin for the workspace.
- **Image Studio** View
  - Prompt (Ctrl+Enter to generate), model, size, quality, background, format, count.
  - Drag images from the file tree to use them as references; a PNG reference can serve as the mask.
  - Partial previews while generating, cancellation, and a gallery of earlier results (copy path, use as reference, reuse prompt).

## Setup

1. Install the plugin (Plugins → install from a local folder or this repository).
2. Enable it for the workspace. It is off by default in every workspace.
3. Choose how images are paid for:
   - **API key**: enter your OpenAI API key in Settings → Plugins → OpenAI Image, or in the image status icon. The key is kept in the system keychain and is only passed to this plugin's tools through stdin.
   - **Codex subscription**: sign in to Codex with ChatGPT in Locus (a paid plan is required), then turn on "Allow this plugin to use your Codex subscription image quota" under Permissions on the plugin's settings page. Only you can turn it on; Locus keeps the sign-in and the plugin never receives it.

## Codex subscription mode

While the permission is on, both tools and Image Studio generate on the subscription:

- The server picks the model, size and quality (currently 1536×1024) and returns one image; there are no partial previews.
- Only the prompt, a transparent background and up to 5 reference images take effect. Masks are not available; a call with a mask or more than 5 references fails with an explanation instead of switching to the API key.
- The tool reply lists the arguments that were ignored and the remaining quota of the subscription's image window.
- Images and `history.jsonl` go to the same output folder as in API key mode; each history entry has `source` set to `codex` or `apiKey`.

Turn the permission off to go back to the API key with all options.

## Settings

| Setting | Default | Scope |
|---|---|---|
| API key | — (needed unless the Codex subscription is allowed) | App |
| API base URL | `https://api.openai.com/v1` | App |
| Organization ID | empty | App |
| Model | `gpt-image-2.6-flare` | App |
| Default size / quality / background / format | `auto` / `auto` / `auto` / `png` | App |
| Output folder | `Locus/generated/images` | Project |
| Show generated images to the model | on | App |
| Show the status icon in the chat input | on | App |

The model is a free-form setting with suggestions (including the 2.5 / 2.6 Flare and Sunburst models), so newer models can be used without a plugin update. Image Studio and the status icon point out combinations a model may reject: `xhigh` / `max` quality is only documented for the 2.5 models, custom sizes for `gpt-image-2` and the 2.5 models, and transparent backgrounds are a preview on `gpt-image-2`.

## Requirements

- Locus with plugin manifest v2 (`contributes`) and TypeScript tool handlers (`toolHandler`, `capabilities`): see `compatibility.locus` in `locus.plugin.json`.
- The tools use only the Python standard library and run with Locus's managed Python.

## Development

```sh
# Unit tests against a local mock of the Images API (no network, no real key)
python -m unittest discover -s tests -v

# Manual testing: start the mock, then set the API base URL to
# http://127.0.0.1:8765/v1 and any API key except "bad-key"
python tests/mock_openai.py --port 8765
```

Prompts containing `trigger-400`, `trigger-429`, `trigger-500`, `trigger-stream-error`, `trigger-slow` or `trigger-url` make the mock return the corresponding failure or variant.

## License

MIT
