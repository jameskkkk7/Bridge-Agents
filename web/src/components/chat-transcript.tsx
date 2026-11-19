import type { RefObject } from "react";

import { Card } from "@/components/ui/card";
import { useLanguage } from "@/i18n";

export interface ViewMessage {
  id: string;
  kind: "user" | "agent" | "system" | "image";
  content: string;
  imageId?: string;
  imageUrl?: string;
}

export default function ChatTranscript({
  messages,
  stream,
  typing,
  loading,
  bottomRef,
}: {
  messages: ViewMessage[];
  stream: string;
  typing: boolean;
  loading: boolean;
  bottomRef: RefObject<HTMLDivElement | null>;
}) {
  const { t, systemText } = useLanguage();

  return (
    <Card className="scrollbar-thin flex min-h-[44dvh] max-h-[56dvh] flex-col gap-3 overflow-y-auto px-4 py-4 sm:px-5 sm:py-5 md:min-h-[46vh] md:max-h-[58vh]">
      {loading && (
        <p className="m-auto text-sm text-muted-foreground">{t("common.loading")}</p>
      )}
      {!loading && messages.length === 0 && !typing && (
        <p className="m-auto max-w-sm text-center text-sm text-muted-foreground">
          {t("chat.empty")}
        </p>
      )}
      {messages.map((message) =>
        message.kind === "system" ? (
          <div
            key={message.id}
            className="mx-auto rounded-full border border-dashed border-border bg-muted px-3 py-1 text-xs text-muted-foreground"
          >
            {systemText(message.content)}
          </div>
        ) : (
          <div
            key={message.id}
            className={
              message.kind === "user"
                ? "ml-auto max-w-[88%] animate-fade-in rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words text-primary-foreground sm:max-w-[78%]"
                : "mr-auto max-w-[88%] animate-fade-in rounded-2xl rounded-bl-md border border-border bg-muted px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words sm:max-w-[78%]"
            }
          >
            {message.kind === "image" ? (
              message.imageUrl ? (
                <img
                  src={message.imageUrl}
                  alt={t("chat.imageAlt")}
                  className="max-w-full rounded-lg"
                />
              ) : (
                <span className="text-muted-foreground">{t("chat.imageLoading")}</span>
              )
            ) : (
              message.content
            )}
          </div>
        ),
      )}
      {stream && (
        <div className="mr-auto max-w-[88%] rounded-2xl rounded-bl-md border border-border bg-muted px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap break-words sm:max-w-[78%]">
          {stream}
          <span className="ml-0.5 inline-block h-4 w-1.5 animate-caret bg-primary align-[-2px]" />
        </div>
      )}
      {typing && !stream && (
        <div className="flex items-center gap-1.5 px-1 py-1.5" aria-label="assistant is typing">
          {[0, 150, 300].map((delay) => (
            <span
              key={delay}
              className="size-1.5 animate-typing rounded-full bg-muted-foreground"
              style={{ animationDelay: `${delay}ms` }}
            />
          ))}
        </div>
      )}
      <div ref={bottomRef} />
    </Card>
  );
}
