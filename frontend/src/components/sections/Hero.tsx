"use client";

import { motion } from "framer-motion";
import { ArrowDown, Download } from "lucide-react";
import Image from "next/image";
import { GithubIcon, LinkedinIcon, GoogleScholarIcon } from "@/components/icons";

const socialLinks = [
  {
    icon: GithubIcon,
    href: "https://github.com/MD-Junayed000",
    label: "GitHub",
  },
  {
    icon: LinkedinIcon,
    href: "https://www.linkedin.com/in/muhammad-junayed-ete20/",
    label: "LinkedIn",
  },
  {
    icon: GoogleScholarIcon,
    href: "https://scholar.google.com/citations?user=wObQzNsAAAAJ&hl=en",
    label: "Google Scholar",
  },
];

export default function Hero() {
  return (
    <section className="relative min-h-screen flex items-center justify-center pt-32 md:pt-40">
      <div className="relative z-10 max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="flex flex-col items-center"
        >
          {/* Profile Image */}
          <div className="relative w-40 h-40 sm:w-52 sm:h-52 mb-6 rounded-full overflow-hidden border-4 border-primary/20 shadow-lg">
            <Image
              src="/images/profile.png"
              alt="Muhammad Junayed"
              fill
              className="object-cover"
              priority
            />
          </div>

          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-foreground mb-4">
            Muhammad Junayed
          </h1>
          <p className="text-lg sm:text-xl text-primary font-medium mb-4">
            AI Engineering Enthusiast
          </p>
          <p className="text-base sm:text-lg text-muted max-w-2xl mx-auto mb-6">
            Specializing in Computer Vision, NLP, and Cloud-Native ML Systems.
            Building intelligent solutions at the intersection of research and
            production.
          </p>

          {/* Social Links */}
          <div className="flex items-center gap-4 mb-8">
            {socialLinks.map((social) => (
              <a
                key={social.label}
                href={social.href}
                target="_blank"
                rel="noopener noreferrer"
                className="p-2 text-muted hover:text-primary border border-border hover:border-primary/50 rounded-full transition-colors"
                aria-label={social.label}
              >
                <social.icon size={20} />
              </a>
            ))}
          </div>

          {/* CTA Buttons */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <a
              href="#projects"
              className="inline-flex items-center gap-2 px-6 py-3 bg-primary hover:bg-primary-hover text-white rounded-lg font-medium transition-colors"
            >
              View Projects
            </a>
            <a
              href="/Muhammad_Junayed_CV.pdf"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-6 py-3 border border-border hover:border-primary/50 hover:bg-surface text-foreground rounded-lg font-medium transition-colors"
            >
              <Download size={18} />
              Download CV
            </a>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1, duration: 0.6 }}
          className="absolute bottom-8 left-1/2 -translate-x-1/2"
        >
          <a href="#about" className="text-muted hover:text-primary transition-colors">
            <ArrowDown size={24} className="animate-bounce" />
          </a>
        </motion.div>
      </div>
    </section>
  );
}
