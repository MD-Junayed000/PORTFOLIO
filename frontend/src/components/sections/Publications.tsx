"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { FileText, ExternalLink, BookOpen } from "lucide-react";
import api from "@/lib/api";
import type { Research as ResearchType } from "@/types";

export default function Publications() {
  const [publications, setPublications] = useState<ResearchType[]>([]);

  useEffect(() => {
    api
      .get("/api/research")
      .then((res) => setPublications(res.data))
      .catch(() => {});
  }, []);

  return (
    <section id="publications" className="py-20 bg-surface-hover/30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
        >
          <h2 className="text-3xl font-bold text-foreground mb-2 text-center">
            Publications
          </h2>
          <p className="text-muted text-center mb-12 max-w-md mx-auto">
            Research papers and academic contributions.
          </p>

          <div className="max-w-3xl mx-auto">
            {publications.length === 0 && (
              <p className="text-center text-muted">No publications to display yet.</p>
            )}
            <div className="relative">
              {/* Timeline line */}
              {publications.length > 0 && (
                <div className="absolute left-4 top-0 bottom-0 w-px bg-border hidden sm:block" />
              )}

              <div className="space-y-6">
                {publications.map((item, idx) => (
                  <motion.div
                    key={item.id}
                    initial={{ opacity: 0, x: -20 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true }}
                    transition={{ duration: 0.3, delay: idx * 0.1 }}
                    className="relative sm:pl-12"
                  >
                    {/* Timeline dot */}
                    <div className="absolute left-2.5 top-5 w-3 h-3 rounded-full bg-primary border-2 border-background hidden sm:block" />

                    <div className="bg-surface border border-border rounded-xl p-5 hover:border-primary/30 hover:shadow-sm transition-all">
                      <div className="flex items-start gap-3">
                        <BookOpen
                          size={18}
                          className="text-primary flex-shrink-0 mt-0.5"
                        />
                        <div className="flex-1 min-w-0">
                          <h3 className="text-sm font-semibold text-foreground mb-1.5">
                            {item.title}
                          </h3>
                          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                            {item.venue && (
                              <span className="flex items-center gap-1">
                                <FileText size={12} />
                                {item.venue}
                              </span>
                            )}
                            {item.year && (
                              <span className="bg-background px-2 py-0.5 rounded border border-border">
                                {item.year}
                              </span>
                            )}
                            <span
                              className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                                item.status === "Published"
                                  ? "bg-green-100 text-green-700"
                                  : "bg-blue-100 text-blue-700"
                              }`}
                            >
                              {item.status}
                            </span>
                          </div>
                        </div>
                        {item.link && (
                          <a
                            href={item.link}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-muted hover:text-primary transition-colors flex-shrink-0"
                            aria-label="View paper"
                          >
                            <ExternalLink size={16} />
                          </a>
                        )}
                      </div>
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
