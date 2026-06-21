"use client";

import { useEffect, useState } from "react";
import { Trash2, Loader2, Mail, Save } from "lucide-react";
import api from "@/lib/api";
import toast from "react-hot-toast";
import type { ContactMessage, ContactInfo } from "@/types";

export default function AdminMessages() {
  const [messages, setMessages] = useState<ContactMessage[]>([]);
  const [loading, setLoading] = useState(true);

  // Contact Info state
  const [contactEmail, setContactEmail] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [contactAddress, setContactAddress] = useState("");
  const [notificationEmails, setNotificationEmails] = useState("");
  const [savingContactInfo, setSavingContactInfo] = useState(false);

  const fetchMessages = () => {
    api
      .get("/api/admin/messages")
      .then((res) => setMessages(res.data))
      .catch(() => setMessages([]))
      .finally(() => setLoading(false));
  };

  const fetchContactInfo = () => {
    api
      .get("/api/admin/contact-info")
      .then((res) => {
        setContactEmail(res.data.email || "");
        setContactPhone(res.data.phone || "");
        setContactAddress(res.data.address || "");
        setNotificationEmails(res.data.notification_emails || "");
      })
      .catch(() => {});
  };

  useEffect(() => {
    fetchMessages();
    fetchContactInfo();
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

  const handleSaveContactInfo = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingContactInfo(true);
    try {
      await api.put("/api/admin/contact-info", {
        email: contactEmail || null,
        phone: contactPhone || null,
        address: contactAddress || null,
        notification_emails: notificationEmails || null,
      });
      toast.success("Contact info updated");
    } catch {
      toast.error("Failed to update contact info");
    } finally {
      setSavingContactInfo(false);
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
      {/* Contact Info Management */}
      <div className="mb-10">
        <h1 className="text-2xl font-bold text-foreground mb-6">
          Contact Information
        </h1>
        <form onSubmit={handleSaveContactInfo} className="max-w-xl space-y-4 bg-surface border border-border rounded-lg p-5">
          <div>
            <label htmlFor="contactEmail" className="block text-sm text-muted mb-1">
              Display Email
            </label>
            <input
              id="contactEmail"
              type="email"
              value={contactEmail}
              onChange={(e) => setContactEmail(e.target.value)}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
              placeholder="your@email.com"
            />
          </div>
          <div>
            <label htmlFor="contactPhone" className="block text-sm text-muted mb-1">
              Phone Number
            </label>
            <input
              id="contactPhone"
              type="text"
              value={contactPhone}
              onChange={(e) => setContactPhone(e.target.value)}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
              placeholder="+880 1876220119"
            />
          </div>
          <div>
            <label htmlFor="contactAddress" className="block text-sm text-muted mb-1">
              Address
            </label>
            <input
              id="contactAddress"
              type="text"
              value={contactAddress}
              onChange={(e) => setContactAddress(e.target.value)}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
              placeholder="City, Country"
            />
          </div>
          <div>
            <label htmlFor="notificationEmails" className="block text-sm text-muted mb-1">
              Notification Emails (comma-separated)
            </label>
            <input
              id="notificationEmails"
              type="text"
              value={notificationEmails}
              onChange={(e) => setNotificationEmails(e.target.value)}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
              placeholder="notify1@email.com, notify2@email.com"
            />
            <p className="text-xs text-muted mt-1">
              These emails will receive notifications when someone submits a contact form.
            </p>
          </div>
          <button
            type="submit"
            disabled={savingContactInfo}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
          >
            {savingContactInfo ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}
            Save Contact Info
          </button>
        </form>
      </div>

      {/* Messages Section */}
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
