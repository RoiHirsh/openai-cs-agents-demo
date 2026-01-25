"use client";

import { ChatKit, useChatKit } from "@openai/chatkit-react";
import React from "react";

interface LeadInfo {
  first_name: string;
  email: string;
  phone: string;
  country: string;
}

type ChatKitPanelProps = {
  initialThreadId?: string | null;
  onThreadChange?: (threadId: string | null) => void;
  onResponseEnd?: () => void;
  onRunnerUpdate?: () => void;
  onRunnerEventDelta?: (events: any[]) => void;
  onRunnerBindThread?: (threadId: string) => void;
  leadInfo?: LeadInfo | null;
};

const CHATKIT_DOMAIN_KEY =
  process.env.NEXT_PUBLIC_CHATKIT_DOMAIN_KEY ?? "domain_pk_localhost_dev";

export function ChatKitPanel({
  initialThreadId,
  onThreadChange,
  onResponseEnd,
  onRunnerUpdate,
  onRunnerEventDelta,
  onRunnerBindThread,
  leadInfo,
}: ChatKitPanelProps) {
  const chatkit = useChatKit({
    api: {
      url: "/chatkit",
      domainKey: CHATKIT_DOMAIN_KEY,
    },
    composer: {
      placeholder: "Message...",
    },
    history: {
      enabled: false,
    },
    theme: {
      colorScheme: "light",
      radius: "round",
      density: "normal",
      color: {
        accent: {
          primary: "#2563eb",
          level: 1,
        },
      },
    },
    initialThread: initialThreadId ?? null,
    startScreen: {
      greeting: leadInfo?.first_name
        ? `Hi ${leadInfo.first_name}!\nMy name is Perry, Senior Portfolio Manager at Lucentive Club.\n\nI'm confident that very soon you'll realize you've come to the right place.\nLet's start with a short conversation.\n\nDo you prefer a call or would you rather we chat here?`
        : "Hi!\nMy name is Perry, Senior Portfolio Manager at Lucentive Club.\n\nI'm confident that very soon you'll realize you've come to the right place.\nLet's start with a short conversation.\n\nDo you prefer a call or would you rather we chat here?",
      prompts: [
        { label: "Chat", prompt: "chat" },
        { label: "Call", prompt: "call" },
      ],
    },
    threadItemActions: {
      feedback: false,
    },
    onThreadChange: ({ threadId }) => onThreadChange?.(threadId ?? null),
    onResponseEnd: () => onResponseEnd?.(),
    onError: ({ error }) => {
      console.error("ChatKit error", error);
    },
    onEffect: async ({ name }) => {
      if (name === "runner_state_update") {
        onRunnerUpdate?.();
      }
      if (name === "runner_event_delta") {
        onRunnerEventDelta?.((arguments as any)?.[0]?.data?.events ?? []);
      }
      if (name === "runner_bind_thread") {
        const tid = (arguments as any)?.[0]?.data?.thread_id;
        if (tid) {
          onRunnerBindThread?.(tid);
        }
      }
    },
  });

  return (
    <div className="flex flex-col h-full flex-1 bg-white shadow-sm border border-gray-200 border-t-0 rounded-xl">
      <div className="bg-blue-600 text-white h-12 px-4 flex items-center rounded-t-xl flex-shrink-0">
        <h2 className="font-semibold text-sm sm:text-base lg:text-lg">
          Customer View
        </h2>
      </div>
      <div className="flex-1 flex flex-col min-h-0 relative">
        <ChatKit
          control={chatkit.control}
          className="flex-1 w-full"
          style={{ height: "100%", width: "100%", minHeight: 0 }}
        />
      </div>
    </div>
  );
}
