"use client";

import { useEffect, useState } from "react";
import { Loader2, Plus, Trash2, Upload } from "lucide-react";
import api from "@/lib/api";
import toast from "react-hot-toast";
import { ExtraLink } from "@/types";

export default function AdminAbout() {
  const [bio, setBio] = useState("");
  const [title, setTitle] = useState("");
  const [subtitle, setSubtitle] = useState("");
  const [education, setEducation] = useState("");
  const [focusArea, setFocusArea] = useState("");
  const [linkedinUrl, setLinkedinUrl] = useState("");
  const [githubUrl, setGithubUrl] = useState("");
  const [scholarUrl, setScholarUrl] = useState("");
  const [extraLinks, setExtraLinks] = useState<ExtraLink[]>([]);
  const [cvFilePath, setCvFilePath] = useState("");
  const [projectDisplayCount, setProjectDisplayCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .get("/api/admin/about")
      .then((res) => {
        setBio(res.data.bio || "");
        setTitle(res.data.title || "");
        setSubtitle(res.data.subtitle || "");
        setEducation(res.data.education || "");
        setFocusArea(res.data.focus_area || "");
        setLinkedinUrl(res.data.linkedin_url || "");
        setGithubUrl(res.data.github_url || "");
        setScholarUrl(res.data.scholar_url || "");
        setCvFilePath(res.data.cv_file_path || "");
        setProjectDisplayCount(res.data.project_display_count ?? 6);
        if (res.data.extra_links) {
          try {
            setExtraLinks(JSON.parse(res.data.extra_links));
          } catch {
            setExtraLinks([]);
          }
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.put("/api/admin/about", {
        bio,
        title,
        subtitle: subtitle || null,
        education: education || null,
        focus_area: focusArea || null,
        linkedin_url: linkedinUrl || null,
        github_url: githubUrl || null,
        scholar_url: scholarUrl || null,
        extra_links: extraLinks.length > 0 ? JSON.stringify(extraLinks) : null,
        cv_file_path: cvFilePath || null,
        project_display_count: projectDisplayCount,
      });
      toast.success("About updated");
    } catch {
      toast.error("Failed to update");
    } finally {
      setSaving(false);
    }
  };

  const handlePhotoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);
    try {
      await api.post(
        "/api/admin/upload-photo?target=about",
        formData,
        { headers: { "Content-Type": "multipart/form-data" } }
      );
      toast.success("Photo uploaded");
    } catch {
      toast.error("Upload failed");
    }
  };

  const handleCvUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await api.post("/api/admin/upload-cv", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setCvFilePath(res.data.cv_url);
      toast.success("CV uploaded");
    } catch {
      toast.error("CV upload failed");
    }
  };

  const handleDeleteCv = async () => {
    try {
      await api.delete("/api/admin/cv");
      setCvFilePath("");
      toast.success("CV deleted");
    } catch {
      toast.error("Failed to delete CV");
    }
  };

  const addExtraLink = () => {
    setExtraLinks([...extraLinks, { name: "", url: "", icon: "" }]);
  };

  const removeExtraLink = (index: number) => {
    setExtraLinks(extraLinks.filter((_, i) => i !== index));
  };

  const updateExtraLink = (index: number, field: keyof ExtraLink, value: string) => {
    const updated = [...extraLinks];
    updated[index] = { ...updated[index], [field]: value };
    setExtraLinks(updated);
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
      <h1 className="text-2xl font-bold text-foreground mb-6">Edit About</h1>

      <form onSubmit={handleSave} className="max-w-2xl space-y-6">
        <div>
          <label htmlFor="title" className="block text-sm text-muted mb-1">
            Title
          </label>
          <input
            id="title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
            placeholder="Your professional title"
          />
        </div>

        <div>
          <label htmlFor="subtitle" className="block text-sm text-muted mb-1">
            Subtitle (shown in Hero)
          </label>
          <input
            id="subtitle"
            type="text"
            value={subtitle}
            onChange={(e) => setSubtitle(e.target.value)}
            className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
            placeholder="e.g. AI Engineering Enthusiast"
          />
        </div>

        <div>
          <label htmlFor="focusArea" className="block text-sm text-muted mb-1">
            Focus Area / Specialization
          </label>
          <textarea
            id="focusArea"
            value={focusArea}
            onChange={(e) => setFocusArea(e.target.value)}
            rows={3}
            className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary resize-none"
            placeholder="Describe your specialization..."
          />
        </div>

        <div>
          <label htmlFor="bio" className="block text-sm text-muted mb-1">
            Bio
          </label>
          <textarea
            id="bio"
            value={bio}
            onChange={(e) => setBio(e.target.value)}
            rows={6}
            className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary resize-none"
            placeholder="Write about yourself..."
          />
        </div>

        <div>
          <label htmlFor="education" className="block text-sm text-muted mb-1">
            Education
          </label>
          <textarea
            id="education"
            value={education}
            onChange={(e) => setEducation(e.target.value)}
            rows={3}
            className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary resize-none"
            placeholder="Your educational background..."
          />
        </div>

        <div>
          <label htmlFor="photo" className="block text-sm text-muted mb-1">
            Profile Photo
          </label>
          <input
            id="photo"
            type="file"
            accept="image/*"
            onChange={handlePhotoUpload}
            className="text-sm text-muted file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:bg-surface file:text-foreground hover:file:bg-surface-hover"
          />
        </div>

        {/* Social Links */}
        <div className="border-t border-border pt-6">
          <h2 className="text-lg font-semibold text-foreground mb-4">Social Links</h2>

          <div className="space-y-4">
            <div>
              <label htmlFor="linkedinUrl" className="block text-sm text-muted mb-1">
                LinkedIn URL
              </label>
              <input
                id="linkedinUrl"
                type="url"
                value={linkedinUrl}
                onChange={(e) => setLinkedinUrl(e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                placeholder="https://linkedin.com/in/..."
              />
            </div>

            <div>
              <label htmlFor="githubUrl" className="block text-sm text-muted mb-1">
                GitHub URL
              </label>
              <input
                id="githubUrl"
                type="url"
                value={githubUrl}
                onChange={(e) => setGithubUrl(e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                placeholder="https://github.com/..."
              />
            </div>

            <div>
              <label htmlFor="scholarUrl" className="block text-sm text-muted mb-1">
                Google Scholar URL
              </label>
              <input
                id="scholarUrl"
                type="url"
                value={scholarUrl}
                onChange={(e) => setScholarUrl(e.target.value)}
                className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                placeholder="https://scholar.google.com/..."
              />
            </div>
          </div>
        </div>

        {/* Extra Custom Links */}
        <div className="border-t border-border pt-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-foreground">Extra Links</h2>
            <button
              type="button"
              onClick={addExtraLink}
              className="inline-flex items-center gap-1 px-3 py-1.5 text-xs bg-surface border border-border rounded-lg text-foreground hover:bg-surface-hover transition-colors"
            >
              <Plus size={14} />
              Add Link
            </button>
          </div>

          {extraLinks.length === 0 && (
            <p className="text-sm text-muted">No extra links added.</p>
          )}

          <div className="space-y-3">
            {extraLinks.map((link, index) => (
              <div key={index} className="flex items-center gap-2">
                <input
                  type="text"
                  value={link.name}
                  onChange={(e) => updateExtraLink(index, "name", e.target.value)}
                  className="flex-1 bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                  placeholder="Label"
                />
                <input
                  type="url"
                  value={link.url}
                  onChange={(e) => updateExtraLink(index, "url", e.target.value)}
                  className="flex-[2] bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                  placeholder="https://..."
                />
                <button
                  type="button"
                  onClick={() => removeExtraLink(index)}
                  className="p-2 text-red-400 hover:text-red-300 transition-colors"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* CV Upload */}
        <div className="border-t border-border pt-6">
          <h2 className="text-lg font-semibold text-foreground mb-4">CV / Resume</h2>

          {cvFilePath ? (
            <div className="flex items-center gap-3 mb-3">
              <span className="text-sm text-foreground">
                Current CV: <span className="text-primary">{cvFilePath.split("/").pop()}</span>
              </span>
              <button
                type="button"
                onClick={handleDeleteCv}
                className="inline-flex items-center gap-1 px-2 py-1 text-xs text-red-400 border border-red-400/30 rounded hover:bg-red-400/10 transition-colors"
              >
                <Trash2 size={12} />
                Delete
              </button>
            </div>
          ) : (
            <p className="text-sm text-muted mb-3">No CV uploaded.</p>
          )}

          <label className="inline-flex items-center gap-2 px-4 py-2 bg-surface border border-border rounded-lg text-sm text-foreground hover:bg-surface-hover cursor-pointer transition-colors">
            <Upload size={16} />
            Upload CV (PDF)
            <input
              type="file"
              accept=".pdf"
              onChange={handleCvUpload}
              className="hidden"
            />
          </label>
        </div>

        <button
          type="submit"
          disabled={saving}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
        >
          {saving && <Loader2 size={14} className="animate-spin" />}
          Save Changes
        </button>
      </form>
    </div>
  );
}
