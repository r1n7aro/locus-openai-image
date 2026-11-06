# OpenAI Image（Locus 插件）

[English](README.md)

在 Locus 中通过 OpenAI Images API 生成和编辑图片：为模型提供两个工具，在输入栏提供状态图标，另附 **Image Studio** View，可以直接生图。可以用自己的 OpenAI API Key 付费；如果你允许，也可以通过 Codex 使用 ChatGPT 订阅的生图额度。

## 功能

- **模型工具**
  - `image_generate`：文生图。参数：prompt、size、quality、background、outputFormat、n（1–4）、fileName、model。
  - `image_edit`：编辑或合成工作区内的图片，可附 PNG 蒙版。
  - 图片保存到输出目录（默认 `Locus/generated/images`），每张图在该目录的 `history.jsonl` 中记一行。
  - 工具结果包含保存路径、改写后的提示词和 token 用量；开启"把生成的图片回传给模型"时同时附上图片。
- **输入栏状态图标**
  - 显示是否正在生成（模型调用和 Image Studio 都算）、是否缺少 API Key，以及上次的错误。
  - 弹窗内有常用默认参数、API Key 输入框、最近一次结果，以及打开 Image Studio、完整设置、隐藏图标、在此工作区禁用等快捷操作。
- **Image Studio** View
  - 提示词（Ctrl+Enter 生成）、模型、尺寸、质量、背景、格式、张数。
  - 从文件树拖入图片作为参考图，PNG 参考图可以设为蒙版。
  - 生成时显示中间预览，可取消；图库列出历史结果，可复制路径、用作参考图、复用提示词。

## 使用

1. 安装插件（插件 → 从本地文件夹或本仓库安装）。
2. 在工作区中启用。插件在所有工作区默认关闭。
3. 选择付费方式：
   - **API Key**：在 设置 → 插件 → OpenAI Image 或图片状态图标中填写 OpenAI API Key。Key 保存在系统钥匙串中，只通过 stdin 交给本插件的工具。
   - **Codex 订阅**：在 Locus 中用 ChatGPT 登录 Codex（需要付费计划），然后在插件设置页的"授权"中打开"允许此插件使用你的 Codex 订阅生图额度"。只有你能打开这个开关；登录凭据由 Locus 保管，插件拿不到。

## Codex 订阅模式

开关打开时，两个工具和 Image Studio 都在订阅上生图：

- 模型、尺寸和质量由服务端决定（目前为 1536×1024），每次返回一张图，没有中间预览。
- 只有提示词、透明背景和最多 5 张参考图生效。不支持蒙版；带蒙版或超过 5 张参考图的调用会直接报错说明原因，不会自动改用 API Key。
- 工具回复会列出被忽略的参数，以及订阅生图窗口的额度用量。
- 图片和 `history.jsonl` 与 API Key 模式使用同一个输出目录；每条历史记录的 `source` 为 `codex` 或 `apiKey`。

关闭开关即可回到 API Key 模式，使用全部参数。

## 设置项

| 设置 | 默认值 | 作用范围 |
|---|---|---|
| API Key | —（未允许使用 Codex 订阅时需要） | 应用 |
| 接口地址 | `https://api.openai.com/v1` | 应用 |
| 组织 ID | 空 | 应用 |
| 模型 | `gpt-image-2.6-flare` | 应用 |
| 默认尺寸 / 质量 / 背景 / 格式 | `auto` / `auto` / `auto` / `png` | 应用 |
| 输出目录 | `Locus/generated/images` | 项目 |
| 把生成的图片回传给模型 | 开 | 应用 |
| 在输入栏显示状态图标 | 开 | 应用 |

模型是可自由填写的设置，附建议列表（包括 2.5 / 2.6 的 Flare 和 Sunburst），新模型无需更新插件即可使用。Image Studio 和状态图标会提示模型可能拒绝的参数组合：`xhigh` / `max` 质量只写明了 2.5 系列支持，自定义尺寸只有 `gpt-image-2` 和 2.5 系列支持，`gpt-image-2` 的透明背景还是预览功能。

## 要求

- 支持插件 manifest v2（`contributes`）和 TypeScript 工具处理器（`toolHandler`、`capabilities`）的 Locus，版本范围见 `locus.plugin.json` 中的 `compatibility.locus`。
- 工具只使用 Python 标准库，由 Locus 托管的 Python 运行。

## 开发

```sh
# 针对本地模拟服务的单元测试（不联网，不需要真实 Key）
python -m unittest discover -s tests -v

# 手动测试：启动模拟服务，把接口地址设为 http://127.0.0.1:8765/v1，
# API Key 填除 "bad-key" 以外的任意值
python tests/mock_openai.py --port 8765
```

提示词中包含 `trigger-400`、`trigger-429`、`trigger-500`、`trigger-stream-error`、`trigger-slow` 或 `trigger-url` 时，模拟服务返回对应的错误或变体。

## 许可

MIT
