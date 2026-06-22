"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Mail, Phone, Send, MapPin } from "lucide-react";
import api from "@/lib/api";
import toast from "react-hot-toast";
import { ContactInfo } from "@/types";

export default function Contact() {
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    message: "",
  });
  const [sending, setSending] = useState(false);
  const [contactInfo, setContactInfo] = useState<ContactInfo | null>(null);

  useEffect(() => {
    api
      .get("/api/contact-info")
      .then((res) => setContactInfo(res.data))
      .catch(() => {});
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.email || !formData.message) {
      toast.error("Please fill in all fields");
      return;
    }
    setSending(true);
    try {
      await api.post("/api/contact", formData);
      toast.success("Message sent successfully!");
      setFormData({ name: "", email: "", message: "" });
    } catch {
      toast.error("Failed to send message. Please try again.");
    } finally {
      setSending(false);
    }
  };

  const displayEmail = contactInfo?.email || "mdjunayed573@gmail.com";
  const displayPhone = contactInfo?.phone || "+880 1876220119";
  const displayAddress = contactInfo?.address;

  return (
    <section id="contact" className="py-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
        >
          <h2 className="text-3xl font-bold text-foreground mb-2 text-center">
            Get in Touch
          </h2>
          <p className="text-muted text-center mb-12 max-w-md mx-auto">
            Open to collaboration, research opportunities, and interesting
            projects.
          </p>

          <div className="grid md:grid-cols-2 gap-10 max-w-4xl mx-auto">
            {/* Contact Form */}
            <div className="bg-surface border border-border rounded-xl p-6">
              <h3 className="text-lg font-semibold text-foreground mb-4">
                Send a Message
              </h3>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label htmlFor="name" className="block text-sm text-muted mb-1">
                    Name
                  </label>
                  <input
                    type="text"
                    id="name"
                    value={formData.name}
                    onChange={(e) =>
                      setFormData({ ...formData, name: e.target.value })
                    }
                    className="w-full px-4 py-2.5 bg-background border border-border rounded-lg text-sm text-foreground placeholder:text-muted focus:outline-none focus:border-primary transition-colors"
                    placeholder="Your name"
                  />
                </div>
                <div>
                  <label htmlFor="email" className="block text-sm text-muted mb-1">
                    Email
                  </label>
                  <input
                    type="email"
                    id="email"
                    value={formData.email}
                    onChange={(e) =>
                      setFormData({ ...formData, email: e.target.value })
                    }
                    className="w-full px-4 py-2.5 bg-background border border-border rounded-lg text-sm text-foreground placeholder:text-muted focus:outline-none focus:border-primary transition-colors"
                    placeholder="your@email.com"
                  />
                </div>
                <div>
                  <label htmlFor="message" className="block text-sm text-muted mb-1">
                    Message
                  </label>
                  <textarea
                    id="message"
                    rows={4}
                    value={formData.message}
                    onChange={(e) =>
                      setFormData({ ...formData, message: e.target.value })
                    }
                    className="w-full px-4 py-2.5 bg-background border border-border rounded-lg text-sm text-foreground placeholder:text-muted focus:outline-none focus:border-primary transition-colors resize-none"
                    placeholder="Your message..."
                  />
                </div>
                <button
                  type="submit"
                  disabled={sending}
                  className="w-full inline-flex items-center justify-center gap-2 px-6 py-3 bg-primary hover:bg-primary-hover text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Send size={16} />
                  {sending ? "Sending..." : "Send Message"}
                </button>
              </form>
            </div>

            {/* Contact Info */}
            <div className="space-y-6">
              <div className="bg-surface border border-border rounded-xl p-6">
                <h3 className="text-lg font-semibold text-foreground mb-4">
                  Contact Information
                </h3>
                <div className="space-y-4">
                  <a
                    href={`mailto:${displayEmail}`}
                    className="flex items-center gap-3 text-muted hover:text-primary transition-colors group"
                  >
                    <div className="p-2 bg-background border border-border rounded-lg group-hover:border-primary/50 transition-colors">
                      <Mail size={18} />
                    </div>
                    <div>
                      <p className="text-xs text-muted">Email</p>
                      <p className="text-sm text-foreground">{displayEmail}</p>
                    </div>
                  </a>
                  <a
                    href={`tel:${displayPhone.replace(/\s/g, "")}`}
                    className="flex items-center gap-3 text-muted hover:text-primary transition-colors group"
                  >
                    <div className="p-2 bg-background border border-border rounded-lg group-hover:border-primary/50 transition-colors">
                      <Phone size={18} />
                    </div>
                    <div>
                      <p className="text-xs text-muted">Phone</p>
                      <p className="text-sm text-foreground">{displayPhone}</p>
                    </div>
                  </a>
                  {displayAddress && (
                    <div className="flex items-center gap-3 text-muted group">
                      <div className="p-2 bg-background border border-border rounded-lg transition-colors">
                        <MapPin size={18} />
                      </div>
                      <div>
                        <p className="text-xs text-muted">Address</p>
                        <p className="text-sm text-foreground">{displayAddress}</p>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
