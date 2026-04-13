import { memo, useState, useCallback } from "react";
import { User, XCircle, RefreshCw, Copy, Check } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { formatTimestamp } from "@/lib/formatters";
import type { AgentMessage } from "@/types/agent";
import { AgentAvatar } from "./AgentAvatar";
import { RunCompleteCard } from "./RunCompleteCard";

const remarkPlugins = [remarkGfm];
const rehypePlugins = [rehypeHighlight];

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [text]);
  return (
    <button
      onClick={handleCopy}
      className="absolute top-2 right-2 p-1.5 rounded-lg bg-[#161822]/80 hover:bg-[#161822] text-[#6B7080] hover:text-[#8B8FA3] opacity-0 group-hover:opacity-100 transition-all duration-200"
      title={copied ? "Copied" : "Copy"}
    >
      {copied ? <Check className="h-3.5 w-3.5 text-[#34D399]" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
}

function getRetryHint(content: string): string {
  const lower = content.toLowerCase();
  if (lower.includes("timeout") || lower.includes("timed out")) {
    return "Execution timed out. Try simplifying the strategy or reducing the number of assets.";
  }
  if (lower.includes("api") || lower.includes("rate limit") || lower.includes("429") || lower.includes("500") || lower.includes("502") || lower.includes("503")) {
    return "API call failed. Please retry later.";
  }
  return "Execution failed. Click to retry.";
}

interface Props {
  msg: AgentMessage;
  onRetry?: (msg: AgentMessage) => void;
}

export const MessageBubble = memo(function MessageBubble({ msg, onRetry }: Props) {
  const ts = msg.timestamp ? formatTimestamp(msg.timestamp) : null;

  if (msg.type === "user") {
    return (
      <div className="flex justify-end gap-3 group">
        <div className="max-w-[72%] rounded-2xl rounded-tr-sm bg-[#F0A050]/10 border border-[#F0A050]/20 px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap text-[#E8E9F0] backdrop-blur-2xl">
          {msg.content}
          {ts && <span className="block text-[9px] opacity-40 text-right mt-1.5 text-[#F0A050] font-mono">{ts}</span>}
        </div>
        <div className="h-8 w-8 rounded-full bg-[#F0A050]/10 border border-[#F0A050]/20 flex items-center justify-center shrink-0 mt-0.5">
          <User className="h-4 w-4 text-[#F0A050]" />
        </div>
      </div>
    );
  }

  if (msg.type === "answer") {
    return (
      <div className="flex gap-3 group">
        <AgentAvatar />
        <div className="flex-1 min-w-0 relative">
          <CopyButton text={msg.content} />
          <div className="rounded-2xl rounded-tl-sm bg-[#0F1117] border border-[#1E2035]/50 px-4 py-3">
            <div className="prose prose-sm dark:prose-invert max-w-none leading-relaxed
              prose-table:border prose-table:border-[#1E2035]/50
              prose-th:bg-[#161822] prose-th:px-3 prose-th:py-1.5
              prose-td:px-3 prose-td:py-1.5
              prose-th:text-left prose-th:text-xs prose-th:font-medium prose-td:text-xs
              prose-code:text-[#F0A050] prose-code:bg-[#161822] prose-code:px-1 prose-code:rounded
              prose-a:text-[#F0A050] prose-a:no-underline hover:prose-a:underline
              prose-headings:text-[#E8E9F0]">
              <ReactMarkdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins}>{msg.content}</ReactMarkdown>
            </div>
          </div>
          {ts && <span className="text-[9px] text-[#6B7080] mt-1 block opacity-0 group-hover:opacity-100 transition-opacity duration-200">{ts}</span>}
        </div>
      </div>
    );
  }

  if (msg.type === "run_complete" && msg.runId) {
    return <RunCompleteCard msg={msg} />;
  }

  if (msg.type === "error") {
    const hint = getRetryHint(msg.content);
    return (
      <div className="flex gap-3">
        <AgentAvatar />
        <div className="space-y-2">
          <div className="flex items-start gap-2.5 rounded-2xl rounded-tl-sm border border-[#F87171]/20 bg-[#F87171]/5 px-4 py-3 backdrop-blur-2xl">
            <XCircle className="h-4 w-4 text-[#F87171] shrink-0 mt-0.5 drop-shadow-[0_0_6px_rgba(248,113,113,0.6)]" />
            <p className="text-sm text-[#F87171] leading-relaxed">{msg.content}</p>
          </div>
          {onRetry && (
            <button
              onClick={() => onRetry(msg)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs text-[#A0A4B8] hover:text-[#E8E9F0] hover:bg-[#0F1117] border border-transparent hover:border-[#1E2035]/50 transition-all duration-200"
              title={hint}
            >
              <RefreshCw className="h-3 w-3" />
              <span>{hint}</span>
            </button>
          )}
        </div>
      </div>
    );
  }

  // Fallback: show content for any unhandled message type
  if (msg.content) {
    return (
      <div className="flex gap-3">
        <AgentAvatar />
        <p className="text-sm text-[#A0A4B8] leading-relaxed">{msg.content}</p>
      </div>
    );
  }

  return null;
});
