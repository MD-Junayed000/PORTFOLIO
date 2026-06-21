"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Briefcase } from "lucide-react";
import api from "@/lib/api";
import type { Experience as ExperienceType } from "@/types";

export default function Experience() {
  const [experiences, setExperiences] = useState<ExperienceType[]>([]);

  useEffect(() => {
    api
      .get("/api/experiences")
      .then((res) => setExperiences(res.data))
      .catch(() => {});
  }, []);

  if (experiences.length === 0) {
    return null;
  }

  return (
    <section id="experience" className="py-20 bg-surface-hover/30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
        >
          <h2 className="text-3xl font-bold text-foreground mb-2 text-center">
            Experience
          </h2>
          <p className="text-muted text-center mb-12 max-w-md mx-auto">
            Professional and academic experience.
          </p>

          <div className="max-w-3xl mx-auto">
            <div className="relative">
              {/* Timeline line */}
              <div className="absolute left-4 top-0 bottom-0 w-px bg-border hidden sm:block" />

              <div className="space-y-6">
                {experiences.map((item, idx) => (
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
                        <Briefcase
                          size={18}
                          className="text-primary flex-shrink-0 mt-0.5"
                        />
                        <div className="flex-1 min-w-0">
                          <h3 className="text-base font-semibold text-foreground mb-1">
                            {item.title}
                          </h3>
                          <p className="text-sm text-primary font-medium mb-1">
                            {item.organization}
                          </p>
                          <p className="text-xs text-muted mb-2">
                            {item.period}
                          </p>
                          {item.description && (
                            <p className="text-sm text-muted leading-relaxed">
                              {item.description}
                            </p>
                          )}
                        </div>
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
