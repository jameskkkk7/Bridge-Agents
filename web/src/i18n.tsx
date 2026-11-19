import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Language = "en" | "zh";

const STORAGE_KEY = "bridge-agents.language";

type Vars = Record<string, string | number>;

const en: Record<string, string> = {
  "app.tagline": "review-gated agent runtime",
  "app.chat": "Chat",
  "app.studio": "Studio",
  "app.support": "Support",
  "title.customer": "Customer support",
  "title.studio": "Studio",
  "title.support": "Support desk",
  "customer.areaLabel": "Customer support",
  "theme.toDark": "Switch to dark theme",
  "theme.toLight": "Switch to light theme",
  "staff.badge": "staff",
  "status.connecting": "connecting",
  "status.online": "online",
  "status.reconnecting": "reconnecting…",
  "status.offline": "offline",
  "common.send": "Send",
  "common.refresh": "Refresh",
  "common.reset": "Reset",
  "common.search": "Search",
  "common.delete": "delete",
  "common.close": "Close",
  "common.loading": "Loading…",
  "common.image": "image",

  "chat.connecting": "Connecting to your conversation…",
  "chat.customerView": "customer view",
  "chat.session": "session {id}",
  "chat.preparing": "preparing",
  "chat.demoTitle": "Live demo conversation",
  "chat.empty": "Say hello — or use a demo prompt to see the review gate and a tool call.",
  "chat.placeholder": "Ask the assistant something…",
  "chat.hint": "Enter to send · Shift+Enter for a new line",
  "chat.quickRefund": "Ask about a refund",
  "chat.quickTool": "Try a tool call",
  "chat.toolPrefix": "tool:",
  "chat.imageLoading": "loading image…",
  "chat.imageAlt": "uploaded attachment",
  "chat.imageLoadFailed": "The image could not be loaded.",
  "chat.imageUploadFailed": "The image upload failed.",
  "chat.error": "The server reported an error.",
  "system.takeover": "A teammate has taken over this conversation.",
  "system.release": "The conversation is back with the assistant.",

  "admin.title": "Support desk",
  "admin.subtitle":
    "Watch conversations live, take over when a human should answer, and reply from here — the customer sees it immediately.",
  "admin.noticeTakeoverOn": "Takeover on — the AI stops and its in-flight reply was cancelled.",
  "admin.noticeTakeoverOff": "Takeover released — the assistant answers again.",
  "admin.noticeClosed": "Conversation closed.",
  "admin.needTakeover": "Take over the conversation before replying.",
  "admin.socketNotReady": "The realtime connection is not ready yet.",
  "admin.conversations": "Conversations",
  "admin.shown": "{count} shown",
  "admin.colCustomer": "Customer",
  "admin.colStatus": "Status",
  "admin.colAI": "AI",
  "admin.pick": "Pick a conversation",
  "admin.pickHint": "Select a conversation to review its transcript.",
  "admin.conversation": "Conversation · {name}",
  "admin.takeOver": "Take over",
  "admin.release": "Release to AI",
  "admin.noMessages": "No messages yet.",
  "admin.system": "system",
  "admin.user": "user",
  "admin.agent": "agent",
  "admin.badgeHuman": "human",
  "admin.badgeAssistant": "assistant",
  "admin.status.active": "active",
  "admin.status.closed": "closed",
  "admin.status.archived": "archived",
  "admin.error": "The server reported an error.",
  "admin.placeholderEnabled": "Reply as support… Enter to send, Shift+Enter for a new line",
  "admin.placeholderDisabled": "Take over the conversation to reply",
  "admin.sendReply": "Send reply",

  "studio.title": "Studio",
  "studio.subtitle":
    "The assistant answers from this knowledge base, and every reply still passes the review gate.",
  "studio.flow": "Flow",
  "studio.knowledge": "Knowledge",
  "studio.settings": "Settings",

  "flow.configTitle": "Graph configuration",
  "flow.configHelp":
    "The default flow is system → retrieval → agent → review → end. Saving compiles the graph before it goes live.",
  "flow.toolbar": "Saving compiles the graph before it replaces the live one.",
  "flow.save": "Save & compile",
  "flow.saved": "Flow saved and recompiled.",
  "flow.resetDone": "Saved flow removed — the built-in graph is active again.",
  "flow.invalidJson": "Invalid JSON: {message}",
  "flow.previewTitle": "Compiled preview",
  "flow.previewHelp": "Mermaid source of the live graph. Paste it into mermaid.live to explore it.",

  "knowledge.reindex": "Reindex",
  "knowledge.upload": "Upload document",
  "knowledge.uploading": "Uploading…",
  "knowledge.toolbar": "Uploads and deletes reindex immediately.",
  "knowledge.statsDocuments": "documents",
  "knowledge.statsPassages": "passages",
  "knowledge.statsDims": "{embedder} dims",
  "knowledge.statsTopK": "passages per turn",
  "knowledge.previewTitle": "Retrieval preview",
  "knowledge.previewHelp":
    "Hybrid search: 60% vector + 40% lexical. Exactly what the retrieval node feeds the assistant.",
  "knowledge.vector": "vector",
  "knowledge.lexical": "lexical",
  "knowledge.searchPlaceholder": "Ask the knowledge base…",
  "knowledge.results": "{count} passage(s) in {ms} ms",
  "knowledge.noResults": "No passage passed the score threshold.",
  "knowledge.documentsTitle": "Documents",
  "knowledge.colDocument": "Document",
  "knowledge.colSize": "Size",
  "knowledge.colPassages": "Passages",
  "knowledge.empty": "No documents yet — upload a markdown file.",
  "knowledge.reindexed": "Index rebuilt from the knowledge directory.",
  "knowledge.uploaded": "Uploaded {name} and reindexed.",
  "knowledge.deleted": "Deleted {name}.",
  "settings.modelTitle": "Model configuration",
  "settings.modelHelp":
    "Used by the agent, custom and review nodes. Saving applies immediately to new messages.",
  "settings.baseUrl": "Provider base URL",
  "settings.model": "Model name",
  "settings.apiKey": "API key",
  "settings.apiKeyPlaceholderSet": "Stored encrypted — leave blank to keep it",
  "settings.apiKeyPlaceholderEmpty": "Optional; falls back to the environment key",
  "settings.keySourceRuntime": "Runtime key stored encrypted",
  "settings.keySourceEnvironment": "Using the environment key",
  "settings.keySourceNone": "No key configured",
  "settings.keyEncryptedHint": "the value is never returned by the API",
  "settings.clearKey": "Remove the stored key and fall back to the environment key",
  "settings.temperature": "Temperature",
  "settings.timeout": "Timeout (s)",
  "settings.maxRetries": "Max retries",
  "settings.thinking": "Disable the provider thinking flag",
  "settings.saveModel": "Save & apply",
  "settings.resetModel": "Reset to environment",
  "settings.modelSaved": "Model configuration saved and applied.",
  "settings.modelReset": "Model configuration reset to the environment defaults.",
  "settings.sourceRuntime": "runtime override",
  "settings.sourceEnvironment": "environment",
  "settings.promptTitle": "Support prompt",
  "settings.promptHelp":
    "The role prompt is the system node of the flow. Saving updates the graph, recompiles it and activates it.",
  "settings.promptSourceSaved": "saved graph",
  "settings.promptSourceDefault": "built-in default",
  "settings.savePrompt": "Save prompt",
  "settings.promptSaved": "Prompt saved and the graph recompiled.",
};

const zh: Record<string, string> = {
  "app.tagline": "审核门控 Agent 运行时",
  "app.chat": "聊天",
  "app.studio": "工作台",
  "app.support": "客服",
  "title.customer": "客户在线支持",
  "title.studio": "工作台",
  "title.support": "客服台",
  "customer.areaLabel": "客户在线支持",
  "theme.toDark": "切换到深色主题",
  "theme.toLight": "切换到浅色主题",
  "staff.badge": "客服 / 管理员",
  "status.connecting": "连接中",
  "status.online": "在线",
  "status.reconnecting": "重新连接…",
  "status.offline": "离线",
  "common.send": "发送",
  "common.refresh": "刷新",
  "common.reset": "重置",
  "common.search": "搜索",
  "common.delete": "删除",
  "common.close": "关闭",
  "common.loading": "加载中…",
  "common.image": "图片",

  "chat.connecting": "正在连接会话…",
  "chat.customerView": "客户视角",
  "chat.session": "会话 {id}",
  "chat.preparing": "准备中",
  "chat.demoTitle": "演示会话",
  "chat.empty": "发一句问候，或点下面的示例，看看审核门禁和工具调用。",
  "chat.placeholder": "向助手提问…",
  "chat.hint": "Enter 发送 · Shift+Enter 换行",
  "chat.quickRefund": "问退款问题",
  "chat.quickTool": "试用工具调用",
  "chat.toolPrefix": "工具：",
  "chat.imageLoading": "图片加载中…",
  "chat.imageAlt": "上传的图片",
  "chat.imageLoadFailed": "图片加载失败。",
  "chat.imageUploadFailed": "图片上传失败。",
  "chat.error": "服务器返回了一个错误。",
  "system.takeover": "客服已接管本次会话。",
  "system.release": "会话已交还给助手。",

  "admin.title": "客服台",
  "admin.subtitle": "实时查看会话，需要真人时接管并直接回复 —— 客户会立即看到。",
  "admin.noticeTakeoverOn": "已接管 —— AI 停止生成，在途回复已取消。",
  "admin.noticeTakeoverOff": "已释放 —— 助手重新开始回复。",
  "admin.noticeClosed": "会话已关闭。",
  "admin.needTakeover": "请先接管会话再回复。",
  "admin.socketNotReady": "实时连接尚未就绪。",
  "admin.conversations": "会话列表",
  "admin.shown": "显示 {count} 条",
  "admin.colCustomer": "客户",
  "admin.colStatus": "状态",
  "admin.colAI": "AI",
  "admin.pick": "选择一个会话",
  "admin.pickHint": "选择会话查看完整记录。",
  "admin.conversation": "会话 · {name}",
  "admin.takeOver": "接管",
  "admin.release": "交还 AI",
  "admin.noMessages": "还没有消息。",
  "admin.system": "系统",
  "admin.user": "客户",
  "admin.agent": "客服",
  "admin.badgeHuman": "人工",
  "admin.badgeAssistant": "助手",
  "admin.status.active": "进行中",
  "admin.status.closed": "已关闭",
  "admin.status.archived": "已归档",
  "admin.error": "服务器返回了一个错误。",
  "admin.placeholderEnabled": "以客服身份回复… Enter 发送，Shift+Enter 换行",
  "admin.placeholderDisabled": "接管会话后可在此回复",
  "admin.sendReply": "发送回复",

  "studio.title": "工作台",
  "studio.subtitle": "助手基于这个知识库回答，每条回复仍然要经过审核门禁。",
  "studio.flow": "流程",
  "studio.knowledge": "知识库",
  "studio.settings": "配置",

  "flow.configTitle": "流程配置",
  "flow.configHelp":
    "默认流程：system → retrieval → agent → review → end。保存前会先编译，跑不起来的配置不会生效。",
  "flow.toolbar": "保存时会先编译，通过后才替换线上流程。",
  "flow.save": "保存并编译",
  "flow.saved": "流程已保存并重新编译。",
  "flow.resetDone": "已删除保存的流程，恢复内置流程。",
  "flow.invalidJson": "JSON 无效：{message}",
  "flow.previewTitle": "编译预览",
  "flow.previewHelp": "当前流程的 Mermaid 源码，可粘贴到 mermaid.live 查看。",

  "knowledge.reindex": "重建索引",
  "knowledge.upload": "上传文档",
  "knowledge.uploading": "上传中…",
  "knowledge.toolbar": "上传或删除文档后会立即重建索引。",
  "knowledge.statsDocuments": "文档",
  "knowledge.statsPassages": "段落",
  "knowledge.statsDims": "{embedder} 维",
  "knowledge.statsTopK": "每轮检索段落",
  "knowledge.previewTitle": "检索预览",
  "knowledge.previewHelp": "混合检索：60% 向量 + 40% 词法，正是检索节点喂给助手的内容。",
  "knowledge.vector": "向量",
  "knowledge.lexical": "词法",
  "knowledge.searchPlaceholder": "向知识库提问…",
  "knowledge.results": "{count} 段 · {ms} 毫秒",
  "knowledge.noResults": "没有段落超过分数阈值。",
  "knowledge.documentsTitle": "文档",
  "knowledge.colDocument": "文档",
  "knowledge.colSize": "大小",
  "knowledge.colPassages": "段落",
  "knowledge.empty": "还没有文档 —— 上传一个 Markdown 文件试试。",
  "knowledge.reindexed": "已根据知识库目录重建索引。",
  "knowledge.uploaded": "已上传 {name} 并重建索引。",
  "knowledge.deleted": "已删除 {name}。",
  "settings.modelTitle": "模型配置",
  "settings.modelHelp": "用于 agent、custom 与 review 节点；保存后对新消息立即生效。",
  "settings.baseUrl": "服务地址（Base URL）",
  "settings.model": "模型名称",
  "settings.apiKey": "API Key",
  "settings.apiKeyPlaceholderSet": "已加密保存 —— 留空表示保持不变",
  "settings.apiKeyPlaceholderEmpty": "可选；留空则使用环境变量里的 Key",
  "settings.keySourceRuntime": "使用运行时保存的加密 Key",
  "settings.keySourceEnvironment": "使用环境变量中的 Key",
  "settings.keySourceNone": "尚未配置 Key",
  "settings.keyEncryptedHint": "API 不会返回该值",
  "settings.clearKey": "删除已保存的 Key，改用环境变量",
  "settings.temperature": "温度（Temperature）",
  "settings.timeout": "超时（秒）",
  "settings.maxRetries": "最大重试次数",
  "settings.thinking": "关闭服务商的 thinking 参数",
  "settings.saveModel": "保存并应用",
  "settings.resetModel": "恢复环境默认",
  "settings.modelSaved": "模型配置已保存并应用。",
  "settings.modelReset": "已恢复为环境变量默认的模型配置。",
  "settings.sourceRuntime": "运行时覆盖",
  "settings.sourceEnvironment": "环境变量",
  "settings.promptTitle": "客服提示词",
  "settings.promptHelp": "角色提示词就是流程图里的 system 节点；保存后会更新流程图、重新编译并生效。",
  "settings.promptSourceSaved": "已保存的流程",
  "settings.promptSourceDefault": "内置默认",
  "settings.savePrompt": "保存提示词",
  "settings.promptSaved": "提示词已保存，流程图已重新编译。",
};

const dictionaries: Record<Language, Record<string, string>> = { en, zh };

if (import.meta.env.DEV) {
  const missing = Object.keys(en).filter((key) => !(key in zh));
  if (missing.length) console.warn("i18n: missing zh keys", missing);
}

export function translate(language: Language, key: string, vars?: Vars): string {
  let value = dictionaries[language][key] ?? en[key] ?? key;
  if (vars) {
    for (const [name, replacement] of Object.entries(vars)) {
      value = value.replaceAll(`{${name}}`, String(replacement));
    }
  }
  return value;
}

const SYSTEM_KEYS: Record<string, string> = {
  "A teammate has taken over this conversation.": "system.takeover",
  "The conversation is back with the assistant.": "system.release",
};

export function localizeSystemMessage(language: Language, content: string): string {
  const key = SYSTEM_KEYS[content.trim()];
  return key ? translate(language, key) : content;
}

export function detectLanguage(): Language {
  if (typeof window === "undefined") return "en";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === "en" || stored === "zh") return stored;
  return window.navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en";
}

interface LanguageContextValue {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: string, vars?: Vars) => string;
  systemText: (content: string) => string;
}

const LanguageContext = createContext<LanguageContextValue>({
  language: "en",
  setLanguage: () => undefined,
  t: (key, vars) => translate("en", key, vars),
  systemText: (content) => content,
});

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(detectLanguage);

  useEffect(() => {
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
    window.localStorage.setItem(STORAGE_KEY, language);
  }, [language]);

  const value = useMemo<LanguageContextValue>(
    () => ({
      language,
      setLanguage: setLanguageState,
      t: (key, vars) => translate(language, key, vars),
      systemText: (content) => localizeSystemMessage(language, content),
    }),
    [language],
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage(): LanguageContextValue {
  return useContext(LanguageContext);
}
