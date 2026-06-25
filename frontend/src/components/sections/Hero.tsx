"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ArrowDown, Download } from "lucide-react";
import Image from "next/image";
import { GithubIcon, LinkedinIcon, GoogleScholarIcon } from "@/components/icons";
import api, { absolutizeUrl } from "@/lib/api";
import { About } from "@/types";

const defaultSocialLinks = [
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
  const [about, setAbout] = useState<About | null>(null);

  useEffect(() => {
    api
      .get("/api/about")
      .then((res) => setAbout(res.data))
      .catch(() => {});
  }, []);

  const socialLinks = about
    ? [
        about.github_url && {
          icon: GithubIcon,
          href: about.github_url,
          label: "GitHub",
        },
        about.linkedin_url && {
          icon: LinkedinIcon,
          href: about.linkedin_url,
          label: "LinkedIn",
        },
        about.scholar_url && {
          icon: GoogleScholarIcon,
          href: about.scholar_url,
          label: "Google Scholar",
        },
      ].filter(Boolean) as { icon: typeof GithubIcon; href: string; label: string }[]
    : defaultSocialLinks;

  // Use default links if none are configured
  const displayLinks = socialLinks.length > 0 ? socialLinks : defaultSocialLinks;

  const subtitle = about?.subtitle || "AI Engineering Enthusiast";
  const focusArea =
    about?.focus_area ||
    "Specializing in Computer Vision, NLP, and Cloud-Native ML Systems. Building intelligent solutions at the intersection of research and production.";

  // The CV is served by the backend at ``/api/cv/Muhammad_Junayed_CV.pdf``.
  // ``about.cv_file_path`` will already be that path (set by the
  // backend's GET /api/about), and ``absolutizeUrl`` prepends the API
  // base URL so the browser can open it directly. If the backend has no
  // CV file on disk, ``cv_file_path`` is null and the link is hidden.
  const cvUrl = absolutizeUrl(about?.cv_file_path);
  const cvDownloadName = "Muhammad_Junayed_CV.pdf";

  // Profile image: use API photo_url if available, fallback to static image
  const profileImageSrc = about?.photo_url
    ? absolutizeUrl(about.photo_url) ?? about.photo_url
    : "/images/profile.png";

  return (
    <section className="relative min-h-screen flex items-center justify-center pt-40">
      <div className="relative z-10 max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="flex flex-col items-center"
        >
          {/* Profile Image */}
          <div className="relative w-48 h-48 sm:w-60 sm:h-60 mb-6 rounded-full overflow-hidden border-4 border-primary/20 shadow-lg">
            <Image
              src={profileImageSrc}
              alt="Muhammad Junayed"
              fill
              className="object-cover"
              priority
            />
          </div>

          <h1 className="text-3xl sm:text-4xl lg:text-5xl font-bold text-foreground mb-4">
            Muhammad Junayed
          </h1>
          <p className="text-lg sm:text-xl text-primary font-medium mb-4">
            {subtitle}
          </p>
          <p className="text-base sm:text-lg text-muted max-w-2xl mx-auto mb-6">
            {focusArea}
          </p>

          {/* Social Links */}
          <div className="flex items-center gap-4 mb-8">
            {displayLinks.map((social) => (
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
            {cvUrl && (
              <a
                href={cvUrl}
                target="_blank"
                rel="noopener noreferrer"
                download={cvDownloadName}
                className="inline-flex items-center gap-2 px-6 py-3 border border-border hover:border-primary/50 hover:bg-surface text-foreground rounded-lg font-medium transition-colors"
              >
                <Download size={18} />
                Download CV
              </a>
            )}
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
