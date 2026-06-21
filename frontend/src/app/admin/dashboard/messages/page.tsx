"use client";

import { useEffect, useState } from "react";
import { Trash2, Loader2, Mail } from "lucide-react";
import api from "@/lib/api";
import toast from "react-hot-toast";
import type { ContactMessage } from "@/types";

export default function AdminMessages() {
  const [messages, setMessages] = useState<ContactMessage[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchMessages = () => {
    api
      .get("/api/admin/messages")
      .then((res) => setMessages(res.data))
      .catch(() => setMessages([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchMessages();
  }, []);

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this message?")) return;
    try {
      await api.delete(`/api/admin/messages/${id}`);
      toast.success("Message deleted");
      fetchMessages();
    } catch {
      toast.error("Delete failed");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={24} className="animate-spin text-muted" />
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-foreground">
          Contact Messages
        </h1>
      </div>

      <div className="space-y-3">
        {messages.length === 0 && (
          <p className="text-sm text-muted text-center py-8">
            No messages received yet.
          </p>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className="bg-surface border border-border rounded-lg p-4"
          >
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-3">
                <Mail size={16} className="text-primary mt-0.5 flex-shrink-0" />
                <div>
                  <h3 className="text-sm font-semibold text-foreground">
                    {msg.name}
                  </h3>
                  <p className="text-xs text-muted">{msg.email}</p>
                  <p className="text-sm text-foreground mt-2">{msg.message}</p>
                  <p className="text-xs text-muted mt-2">{msg.created_at}</p>
                </div>
              </div>
              <button
                onClick={() => handleDelete(msg.id)}
                className="p-2 text-muted hover:text-red-400 transition-colors flex-shrink-0"
                aria-label="Delete"
              >
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
