/**
 * Provider presets used by Studio -> Settings.
 *
 * Every base URL below was checked against the vendor's official documentation
 * on 2026-11-20. See docs/providers.md for the verified table, model-list
 * support and international alternatives.
 */
export interface ModelProviderPreset {
  id: string;
  baseUrl: string;
  apiVersion?: string;
  /** Provider needs an OpenAI-compatible gateway or compatibility layer. */
  gateway?: boolean;
  /** Official documentation for the base URL / compatibility layer. */
  docsUrl: string;
}

export const MODEL_PROVIDERS: ModelProviderPreset[] = [
  {
    id: "openai",
    baseUrl: "https://api.openai.com/v1",
    docsUrl: "https://developers.openai.com/api/docs",
  },
  {
    id: "azure",
    baseUrl: "",
    apiVersion: "2024-10-21",
    docsUrl: "https://learn.microsoft.com/azure/ai-services/openai/reference",
  },
  {
    // Official OpenAI-compatible base URL; /v1 is also accepted by DeepSeek.
    id: "deepseek",
    baseUrl: "https://api.deepseek.com",
    docsUrl: "https://api-docs.deepseek.com/quick_start/your_first_api_call",
  },
  {
    // Beijing shared domain. International: https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    // Production can use the workspace-specific domain documented by Alibaba Cloud.
    id: "qwen",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    docsUrl: "https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope",
  },
  {
    // International alternative: https://api.moonshot.ai/v1
    id: "moonshot",
    baseUrl: "https://api.moonshot.cn/v1",
    docsUrl: "https://platform.kimi.com/docs/api/overview",
  },
  {
    id: "zhipu",
    baseUrl: "https://open.bigmodel.cn/api/paas/v4",
    docsUrl: "https://docs.bigmodel.cn/cn/api/introduction",
  },
  {
    id: "volcengine",
    baseUrl: "https://ark.cn-beijing.volces.com/api/v3",
    docsUrl: "https://docs.volcengine.com/docs/ark/models-api",
  },
  {
    id: "baidu",
    baseUrl: "https://qianfan.baidubce.com/v2",
    docsUrl: "https://cloud.baidu.com/doc/qianfan/s/Hmh4suq26",
  },
  {
    // Current OpenAI-compatible domain. International: https://api.minimax.io/v1
    id: "minimax",
    baseUrl: "https://api.minimax.cn/v1",
    docsUrl: "https://platform.minimax.cn/docs/api-reference/text-openai-api",
  },
  {
    // International alternative: https://api.siliconflow.com/v1
    id: "siliconflow",
    baseUrl: "https://api.siliconflow.cn/v1",
    docsUrl: "https://docs.siliconflow.cn/cn/userguide/quickstart",
  },
  {
    id: "openrouter",
    baseUrl: "https://openrouter.ai/api/v1",
    docsUrl: "https://openrouter.ai/docs/guides/features/compatibility",
  },
  {
    id: "gemini",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    docsUrl: "https://ai.google.dev/gemini-api/docs/openai",
  },
  {
    // Official OpenAI SDK compatibility layer; chat works, model listing does not.
    id: "anthropic",
    baseUrl: "https://api.anthropic.com/v1",
    gateway: true,
    docsUrl: "https://platform.claude.com/docs/en/cli-sdks-libraries/libraries/openai-sdk",
  },
  {
    // Local Ollama; cloud OpenAI-compatible base URL is https://ollama.com/v1
    id: "ollama",
    baseUrl: "http://127.0.0.1:11434/v1",
    docsUrl: "https://docs.ollama.com/api/openai-compatibility",
  },
  {
    id: "custom",
    baseUrl: "",
    docsUrl: "",
  },
];

export function providerPreset(id: string): ModelProviderPreset | undefined {
  return MODEL_PROVIDERS.find((preset) => preset.id === id);
}
