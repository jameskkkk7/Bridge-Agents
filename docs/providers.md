# Model provider endpoints

The Studio provider presets were checked against the vendors' official
documentation on **2026-11-20**. The source of truth in code is
[`web/src/pages/studio/model-presets.ts`](../web/src/pages/studio/model-presets.ts).

| Provider | Base URL used | Model list | Check without a key (2026-11-20) | Official documentation |
|---|---|---|---|---|
| OpenAI | `https://api.openai.com/v1` | `GET /models` | 401 | [docs](https://developers.openai.com/api/docs) |
| Azure OpenAI | `https://<resource>.openai.azure.com` (user-provided; API version required) | `GET /openai/deployments?api-version=…` | not testable without a resource | [docs](https://learn.microsoft.com/azure/ai-services/openai/reference) |
| DeepSeek | `https://api.deepseek.com` | `GET /models` | 401 | [docs](https://api-docs.deepseek.com/quick_start/your_first_api_call) |
| Alibaba Cloud (Qwen) | `https://dashscope.aliyuncs.com/compatible-mode/v1` | compatible-mode list not documented; manual fallback if it fails | 401 | [docs](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope) |
| Kimi (Moonshot) | `https://api.moonshot.cn/v1` | `GET /v1/models` | 401 | [docs](https://platform.kimi.com/docs/api/overview) |
| Zhipu GLM | `https://open.bigmodel.cn/api/paas/v4` | not documented for the compatible endpoint; manual fallback if it fails | 401 | [docs](https://docs.bigmodel.cn/cn/api/introduction) |
| Volcengine Ark | `https://ark.cn-beijing.volces.com/api/v3` | `GET /models` | 401 | [docs](https://docs.volcengine.com/docs/ark/models-api) |
| Baidu Qianfan | `https://qianfan.baidubce.com/v2` | `GET /models` | 403 | [docs](https://cloud.baidu.com/doc/qianfan/s/Hmh4suq26) |
| MiniMax | `https://api.minimax.cn/v1` | `GET /v1/models` | 401 | [docs](https://platform.minimax.cn/docs/api-reference/text-openai-api) |
| SiliconFlow | `https://api.siliconflow.cn/v1` | `GET /v1/models` | 401 | [docs](https://docs.siliconflow.cn/cn/userguide/quickstart) |
| OpenRouter | `https://openrouter.ai/api/v1` | `GET /models` | 200 | [docs](https://openrouter.ai/docs/guides/features/compatibility) |
| Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | OpenAI-compatible model list returned 404; manual fallback | 404 | [docs](https://ai.google.dev/gemini-api/docs/openai) |
| Anthropic | `https://api.anthropic.com/v1` (OpenAI SDK compatibility layer) | native models API needs `x-api-key`; compatibility layer does not list models; manual fallback | 401 | [docs](https://platform.claude.com/docs/en/cli-sdks-libraries/libraries/openai-sdk) |
| Ollama | `http://127.0.0.1:11434/v1` (cloud: `https://ollama.com/v1`) | `GET /v1/models` | local service not running during the check | [docs](https://docs.ollama.com/api/openai-compatibility) |
| Custom gateway | user-provided | depends on the gateway | — | — |

A 401/403 response means the host and path are reachable and authentication is
enforced; it does not prove the model-list route exists. Providers whose
compatible model list is unavailable fall back to the manual model field in
Studio.

## International / regional alternatives

- Alibaba Cloud international: `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`.
  Alibaba Cloud also recommends workspace-specific domains for production
  (`https://{WorkspaceId}.{region}.maas.aliyuncs.com/compatible-mode/v1`).
- Kimi international: `https://api.moonshot.ai/v1`.
- MiniMax international: `https://api.minimax.io/v1`.
- SiliconFlow international: `https://api.siliconflow.com/v1`.
- Ollama cloud: `https://ollama.com/v1`.

## How model discovery behaves

When an API key is available, Studio asks the provider for its model list and
shows a dropdown. Providers without an OpenAI-compatible model-list endpoint
(Anthropic's compatibility layer, some gateways) or whose list cannot be
reached fall back to a manual model-name field; the API key is never returned
or logged.

## Updating a preset

1. Confirm the base URL and compatibility layer in the vendor's official docs.
2. Update `model-presets.ts` and the table above, including the checked date.
3. Keep `/models` discovery support in mind: `POST /api/v1/admin/runtime-config/model-config/models`
   calls `{base_url}/models` for OpenAI-compatible providers and Azure
   deployments for Azure.
4. Run the web build and the backend tests.
