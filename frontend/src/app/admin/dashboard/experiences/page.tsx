"use client";

import { useEffect, useState, useRef } from "react";
import { Plus, Pencil, Trash2, Loader2, X, Upload } from "lucide-react";
import api from "@/lib/api";
import toast from "react-hot-toast";
import type { Experience } from "@/types";

interface ExperienceForm {
  title: string;
  organization: string;
  period: string;
  description: string;
  logo_url: string;
}

const emptyForm: ExperienceForm = {
  title: "",
  organization: "",
  period: "",
  description: "",
  logo_url: "",
};

export default function AdminExperiences() {
  const [experiences, setExperiences] = useState<Experience[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<ExperienceForm>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleLogoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await api.post("/api/admin/upload-photo", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setForm({ ...form, logo_url: res.data.photo_url });
      toast.success("Logo uploaded");
    } catch {
      toast.error("Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const fetchExperiences = () => {
    api
      .get("/api/experiences")
      .then((res) => setExperiences(res.data))
      .catch(() => setExperiences([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchExperiences();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        title: form.title,
        organization: form.organization,
        period: form.period,
        description: form.description || null,
        logo_url: form.logo_url || null,
      };
      if (editingId) {
        await api.put(`/api/admin/experiences/${editingId}`, payload);
        toast.success("Experience updated");
      } else {
        await api.post("/api/admin/experiences", payload);
        toast.success("Experience created");
      }
      setShowForm(false);
      setEditingId(null);
      setForm(emptyForm);
      fetchExperiences();
    } catch {
      toast.error("Operation failed");
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (exp: Experience) => {
    setForm({
      title: exp.title,
      organization: exp.organization,
      period: exp.period,
      description: exp.description || "",
      logo_url: exp.logo_url || "",
    });
    setEditingId(exp.id);
    setShowForm(true);
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this experience?")) return;
    try {
      await api.delete(`/api/admin/experiences/${id}`);
      toast.success("Experience deleted");
      fetchExperiences();
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
        <h1 className="text-2xl font-bold text-foreground">Experiences</h1>
        <button
          onClick={() => {
            setForm(emptyForm);
            setEditingId(null);
            setShowForm(true);
          }}
          className="inline-flex items-center gap-2 px-3 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Plus size={16} />
          Add Experience
        </button>
      </div>

      {/* Form */}
      {showForm && (
        <div className="mb-6 bg-surface border border-border rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-foreground">
              {editingId ? "Edit Experience" : "New Experience"}
            </h2>
            <button
              onClick={() => setShowForm(false)}
              className="text-muted hover:text-foreground"
            >
              <X size={18} />
            </button>
          </div>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-muted mb-1">Title</label>
                <input
                  type="text"
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-muted mb-1">
                  Organization
                </label>
                <input
                  type="text"
                  value={form.organization}
                  onChange={(e) =>
                    setForm({ ...form, organization: e.target.value })
                  }
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                  required
                />
              </div>
            </div>
            <div>
              <label className="block text-sm text-muted mb-1">
                Period (e.g., Jan 2022 - Present)
              </label>
              <input
                type="text"
                value={form.period}
                onChange={(e) => setForm({ ...form, period: e.target.value })}
                className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                required
              />
            </div>
            <div>
              <label className="block text-sm text-muted mb-1">
                Description
              </label>
              <textarea
                value={form.description}
                onChange={(e) =>
                  setForm({ ...form, description: e.target.value })
                }
                rows={3}
                className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary resize-none"
              />
            </div>
            <div>
              <label className="block text-sm text-muted mb-1">
                Company Logo
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={form.logo_url}
                  onChange={(e) =>
                    setForm({ ...form, logo_url: e.target.value })
                  }
                  className="flex-1 bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                  placeholder="Upload or paste URL..."
                />
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  onChange={handleLogoUpload}
                  className="hidden"
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                  className="inline-flex items-center gap-1 px-3 py-2 bg-background border border-border rounded-lg text-sm text-muted hover:text-foreground hover:border-primary/50 transition-colors disabled:opacity-50"
                >
                  {uploading ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <Upload size={14} />
                  )}
                  Upload
                </button>
              </div>
            </div>
            <button
              type="submit"
              disabled={saving}
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
            >
              {saving && <Loader2 size={14} className="animate-spin" />}
              {editingId ? "Update" : "Create"}
            </button>
          </form>
        </div>
      )}

      {/* Experience list */}
      <div className="space-y-3">
        {experiences.length === 0 && (
          <p className="text-sm text-muted text-center py-8">
            No experiences added yet.
          </p>
        )}
        {experiences.map((exp) => (
          <div
            key={exp.id}
            className="bg-surface border border-border rounded-lg p-4 flex items-center justify-between"
          >
            <div className="flex items-center gap-3">
              {exp.logo_url && (
                <img
                  src={`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}${exp.logo_url}`}
                  alt={exp.organization}
                  className="w-8 h-8 rounded object-cover"
                />
              )}
              <div>
                <h3 className="text-sm font-semibold text-foreground">
                  {exp.title}
                </h3>
                <p className="text-xs text-muted mt-1">
                  {exp.organization} &middot; {exp.period}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => handleEdit(exp)}
                className="p-2 text-muted hover:text-foreground transition-colors"
                aria-label="Edit"
              >
                <Pencil size={14} />
              </button>
              <button
                onClick={() => handleDelete(exp.id)}
                className="p-2 text-muted hover:text-red-400 transition-colors"
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
