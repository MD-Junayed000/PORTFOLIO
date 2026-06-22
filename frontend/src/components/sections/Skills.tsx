"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import api from "@/lib/api";
import type { Skill } from "@/types";

// Map skill names to devicon icon names
const DEVICON_MAP: Record<string, string> = {
  python: "python",
  docker: "docker",
  fastapi: "fastapi",
  "node.js": "nodejs",
  nodejs: "nodejs",
  postgresql: "postgresql",
  react: "react",
  aws: "amazonwebservices",
  "c++": "cplusplus",
  javascript: "javascript",
  typescript: "typescript",
  pytorch: "pytorch",
  tensorflow: "tensorflow",
  java: "java",
  git: "git",
  linux: "linux",
  mongodb: "mongodb",
  redis: "redis",
  nextjs: "nextjs",
  "next.js": "nextjs",
  tailwind: "tailwindcss",
  tailwindcss: "tailwindcss",
  html: "html5",
  css: "css3",
  mysql: "mysql",
  flask: "flask",
  django: "django",
  vue: "vuejs",
  angular: "angularjs",
  kubernetes: "kubernetes",
  nginx: "nginx",
  go: "go",
  rust: "rust",
  php: "php",
  swift: "swift",
  kotlin: "kotlin",
  figma: "figma",
  firebase: "firebase",
  graphql: "graphql",
};

function getDeviconUrl(skillName: string): string | null {
  const key = skillName.toLowerCase().trim();
  const icon = DEVICON_MAP[key];
  if (!icon) return null;
  return `https://cdn.jsdelivr.net/gh/devicons/devicon/icons/${icon}/${icon}-original.svg`;
}

export default function Skills() {
  const [skills, setSkills] = useState<Skill[]>([]);

  useEffect(() => {
    api
      .get("/api/skills")
      .then((res) => setSkills(res.data))
      .catch(() => {});
  }, []);

  // Split skills into two roughly equal rows
  const midpoint = Math.ceil(skills.length / 2);
  const row1 = skills.slice(0, midpoint);
  const row2 = skills.slice(midpoint);

  return (
    <section id="skills" className="py-20 overflow-hidden">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5 }}
        >
          <h2 className="text-3xl font-bold text-foreground mb-12 text-center">
            Skills
          </h2>

          <div className="space-y-4">
            {/* Row 1: scrolls right-to-left */}
            <MarqueeRow skills={row1} direction="left" />

            {/* Row 2: scrolls left-to-right */}
            <MarqueeRow skills={row2} direction="right" />
          </div>

          <p className="text-center text-muted text-sm mt-8">
            Technical skills I acquired or familiar with.
          </p>
        </motion.div>
      </div>
    </section>
  );
}

function MarqueeRow({
  skills,
  direction,
}: {
  skills: Skill[];
  direction: "left" | "right";
}) {
  if (skills.length === 0) return null;

  const animationDirection = direction === "left" ? "normal" : "reverse";

  return (
    <div className="relative overflow-hidden group">
      <div
        className="flex gap-3 w-max"
        style={{
          animation: `marquee-scroll 35s linear infinite`,
          animationDirection,
          willChange: "transform",
        }}
      >
        {/* Render the list twice for seamless infinite scroll */}
        {[...skills, ...skills].map((skill, index) => (
          <span
            key={`${skill.id}-${index}`}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-surface border border-border rounded-full text-sm text-foreground whitespace-nowrap hover:border-primary hover:text-primary transition-colors"
          >
            {getDeviconUrl(skill.name) && (
              <img
                src={getDeviconUrl(skill.name)!}
                alt=""
                width={16}
                height={16}
                className="inline-block"
              />
            )}
            {skill.name}
          </span>
        ))}
      </div>

      <style jsx>{`
        @keyframes marquee-scroll {
          from {
            transform: translateX(0);
          }
          to {
            transform: translateX(-50%);
          }
        }
        .group:hover div {
          animation-play-state: paused;
        }
      `}</style>
    </div>
  );
}
