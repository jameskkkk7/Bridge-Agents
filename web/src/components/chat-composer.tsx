import { useRef } from "react";
import { ArrowUp, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

export const IMAGE_ACCEPT = "image/png,image/jpeg,image/gif,image/webp,image/bmp";

/**
 * Chat input styled after the reference design: one large rounded surface with
 * a multi-line field, an attach button on the left and a circular send button
 * on the right. Enter sends, Shift+Enter adds a line.
 */
export default function ChatComposer({
  value,
  placeholder,
  sendLabel,
  attachLabel,
  disabled = false,
  uploading = false,
  onChange,
  onSend,
  onPickImage,
}: {
  value: string;
  placeholder: string;
  sendLabel: string;
  attachLabel: string;
  disabled?: boolean;
  uploading?: boolean;
  onChange: (value: string) => void;
  onSend: () => void;
  onPickImage: (file: File) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const canSend = !disabled && value.trim().length > 0;

  return (
    <div
      className={cn(
        "flex flex-col gap-1.5 rounded-3xl border border-border bg-card p-2.5 shadow-xs",
        "transition-[border-color,box-shadow] focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/25",
        disabled && "opacity-60",
      )}
    >
      <Textarea
        value={value}
        rows={1}
        placeholder={placeholder}
        disabled={disabled}
        aria-label={placeholder}
        className="max-h-40 min-h-16 resize-none rounded-2xl border-0 bg-transparent px-3 py-2 text-sm shadow-none focus-visible:ring-0"
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            if (canSend) onSend();
          }
        }}
      />
      <div className="flex items-center justify-between gap-2 px-0.5">
        <Button
          type="button"
          variant="secondary"
          size="icon"
          className="size-9 rounded-full"
          onClick={() => fileRef.current?.click()}
          disabled={disabled || uploading}
          aria-label={attachLabel}
          title={attachLabel}
        >
          <Plus />
        </Button>
        <Button
          type="button"
          size="icon"
          className="size-9 rounded-full"
          onClick={onSend}
          disabled={!canSend}
          aria-label={sendLabel}
          title={sendLabel}
        >
          <ArrowUp />
        </Button>
        <input
          ref={fileRef}
          type="file"
          accept={IMAGE_ACCEPT}
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) onPickImage(file);
            event.target.value = "";
          }}
        />
      </div>
    </div>
  );
}
