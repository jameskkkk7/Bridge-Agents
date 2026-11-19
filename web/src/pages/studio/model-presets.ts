export interface ModelProviderPreset {
  id: string;
  baseUrl: string;
  model: string;
  apiVersion?: string;
  /** Vendor exposes no official OpenAI-compatible endpoint. */
  gateway?: boolean;
}

export const MODEL_PROVIDERS: ModelProviderPreset[] = [
  { id: "openai", baseUrl: "https://api.openai.com/v1", model: "gpt-4o-mini" },
  {
    id: "azure",
    baseUrl: "",
    model: "gpt-4o-mini",
    apiVersion: "2024-10-21",
  },
  { id: "deepseek", baseUrl: "https://api.deepseek.com/v1", model: "deepseek-chat" },
  {
    id: "qwen",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: "qwen-plus",
  },
  { id: "moonshot", baseUrl: "https://api.moonshot.cn/v1", model: "moonshot-v1-8k" },
  { id: "zhipu", baseUrl: "https://open.bigmodel.cn/api/paas/v4", model: "glm-4-flash" },
  {
    id: "volcengine",
    baseUrl: "https://ark.cn-beijing.volces.com/api/v3",
    model: "doubao-pro-32k",
  },
  { id: "baidu", baseUrl: "https://qianfan.baidubce.com/v2", model: "ernie-4.0-8k" },
  { id: "minimax", baseUrl: "https://api.minimax.chat/v1", model: "abab6.5s-chat" },
  {
    id: "siliconflow",
    baseUrl: "https://api.siliconflow.cn/v1",
    model: "Qwen/Qwen2.5-7B-Instruct",
  },
  { id: "openrouter", baseUrl: "https://openrouter.ai/api/v1", model: "openai/gpt-4o-mini" },
  {
    id: "gemini",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    model: "gemini-2.0-flash",
  },
  {
    id: "anthropic",
    baseUrl: "",
    model: "claude-sonnet-4-20250514",
    gateway: true,
  },
  { id: "ollama", baseUrl: "http://127.0.0.1:11434/v1", model: "llama3.1" },
  { id: "custom", baseUrl: "", model: "" },
];

export function providerPreset(id: string): ModelProviderPreset | undefined {
  return MODEL_PROVIDERS.find((preset) => preset.id === id);
}
