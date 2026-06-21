"use client";

import { useEffect, useState } from "react";
import { Plus, Pencil, Trash2, Loader2, X } from "lucide-react";
import api from "@/lib/api";
import toast from "react-hot-toast";
import type { Experience } from "@/types";

interface ExperienceForm {
  title: string;
  organization: string;
  period: string;
  description: string;
}

const emptyForm: ExperienceForm = {
  title: "",
  organization: "",
  period: "",
  description: "",
};

export default function AdminExperiences() {
  const [experiences, setExperiences] = useState<Experience[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<ExperienceForm>(emptyForm);
  const [saving, setSaving] = useState(false);

  const fetchExperiences = () => {
    api
      .get("/api/admin/experiences")
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
      if (editingId) {
        await api.put(`/api/admin/experiences/${editingId}`, form);
        toast.success("Experience updated");
      } else {
        await api.post("/api/admin/experiences", form);
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
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                {exp.title}
              </h3>
              <p className="text-xs text-muted mt-1">
                {exp.organization} &middot; {exp.period}
              </p>
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
