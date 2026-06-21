"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ExternalLink } from "lucide-react";
import { GithubIcon } from "@/components/icons";
import Image from "next/image";
import api from "@/lib/api";
import type { Project } from "@/types";

export default function Projects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [filter, setFilter] = useState<string>("All");

  useEffect(() => {
    api
      .get("/api/projects")
      .then((res) => setProjects(res.data))
      .catch(() => {});
  }, []);

  const allTechs = Array.from(
    new Set(
      projects.flatMap((p) =>
        p.tech_stack.split(",").map((t) => t.trim())
      )
    )
  ).slice(0, 8);

  const categories = ["All", ...allTechs];

  const filtered =
    filter === "All"
      ? projects
      : projects.filter((p) =>
          p.tech_stack.toLowerCase().includes(filter.toLowerCase())
        );

  return (
    <section id="projects" className="py-20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
        >
          <h2 className="text-3xl font-bold text-foreground mb-2 text-center">
            Projects
          </h2>
          <p className="text-muted text-center mb-10 max-w-md mx-auto">
            A selection of projects showcasing my work in AI and software engineering.
          </p>

          {/* Filter chips */}
          <div className="flex flex-wrap justify-center gap-2 mb-10">
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setFilter(cat)}
                className={`px-4 py-1.5 text-xs rounded-full border transition-colors font-medium ${
                  filter === cat
                    ? "bg-primary text-white border-primary"
                    : "border-border text-muted hover:text-foreground hover:border-primary/50 bg-surface"
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          {/* Project grid */}
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {filtered.map((project, idx) => (
              <motion.div
                key={project.id}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.3, delay: idx * 0.05 }}
                className="bg-surface border border-border rounded-xl overflow-hidden shadow-sm hover:shadow-md hover:border-primary/30 transition-all group"
              >
                {/* Project Image */}
                {project.image_url && (
                  <div className="relative h-40 bg-surface-hover overflow-hidden">
                    <Image
                      src={project.image_url}
                      alt={project.name}
                      fill
                      className="object-cover group-hover:scale-105 transition-transform duration-300"
                    />
                  </div>
                )}

                <div className="p-5">
                  <h3 className="text-lg font-semibold text-foreground mb-2 group-hover:text-primary transition-colors">
                    {project.name}
                  </h3>
                  <p className="text-sm text-muted mb-4 line-clamp-3">
                    {project.description}
                  </p>
                  <div className="flex flex-wrap gap-1.5 mb-4">
                    {project.tech_stack.split(",").map((tech) => (
                      <span
                        key={tech}
                        className="px-2 py-0.5 text-xs bg-background border border-border rounded-full text-muted"
                      >
                        {tech.trim()}
                      </span>
                    ))}
                  </div>
                  <div className="flex items-center gap-3 pt-2 border-t border-border">
                    {project.repo_url && (
                      <a
                        href={project.repo_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-muted hover:text-primary transition-colors"
                        aria-label="GitHub repository"
                      >
                        <GithubIcon size={16} />
                      </a>
                    )}
                    {project.demo_url && (
                      <a
                        href={project.demo_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-muted hover:text-primary transition-colors"
                        aria-label="Live demo"
                      >
                        <ExternalLink size={16} />
                      </a>
                    )}
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  );
}
