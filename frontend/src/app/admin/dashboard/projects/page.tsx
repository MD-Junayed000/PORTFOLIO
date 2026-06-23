"use client";

import { useEffect, useState, useRef } from "react";
import { Plus, Pencil, Trash2, Loader2, X, Upload, ArrowUp, ArrowDown, Save } from "lucide-react";
import api, { API_BASE_URL } from "@/lib/api";
import toast from "react-hot-toast";
import type { Project } from "@/types";

interface ProjectForm {
  name: string;
  description: string;
  tech_stack: string;
  repo_url: string;
  demo_url: string;
  image_url: string;
  order: number;
}

const emptyForm: ProjectForm = {
  name: "",
  description: "",
  tech_stack: "",
  repo_url: "",
  demo_url: "",
  image_url: "",
  order: 0,
};

export default function AdminProjects() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<ProjectForm>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [displayCount, setDisplayCount] = useState<number>(6);
  const [reordering, setReordering] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      // Editing an existing project → persist to its row (so the About profile
      // photo is never clobbered by a project image upload). Creating a new
      // project → just upload to Cloudinary and stash the URL locally until
      // the project row is created.
      const params = editingId
        ? `?target=project&target_id=${editingId}`
        : "?target=none";
      const res = await api.post(`/api/admin/upload-photo${params}`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setForm({ ...form, image_url: res.data.photo_url });
      toast.success("Image uploaded");
    } catch {
      toast.error("Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const fetchProjects = () => {
    api
      .get("/api/projects")
      .then((res) => setProjects(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchProjects();
    // Load display count from server (about settings)
    api
      .get("/api/about")
      .then((res) => {
        const count = res.data?.project_display_count;
        if (count && count > 0) setDisplayCount(count);
      })
      .catch(() => {});
  }, []);

  const handleDisplayCountSave = async () => {
    try {
      // Fetch current about data, then update with new display count
      const aboutRes = await api.get("/api/about");
      const aboutData = aboutRes.data;
      await api.put("/api/admin/about", {
        bio: aboutData.bio || "Profile not yet configured.",
        title: aboutData.title || "Portfolio",
        photo_url: aboutData.photo_url,
        education: aboutData.education,
        focus_area: aboutData.focus_area,
        subtitle: aboutData.subtitle,
        linkedin_url: aboutData.linkedin_url,
        github_url: aboutData.github_url,
        scholar_url: aboutData.scholar_url,
        extra_links: aboutData.extra_links,
        cv_file_path: aboutData.cv_file_path,
        project_display_count: displayCount,
      });
      toast.success(`Display count set to ${displayCount}`);
    } catch {
      toast.error("Failed to save display count");
    }
  };

  const moveProject = async (index: number, direction: "up" | "down") => {
    const newProjects = [...projects];
    const swapIndex = direction === "up" ? index - 1 : index + 1;
    if (swapIndex < 0 || swapIndex >= newProjects.length) return;

    // Swap the items
    [newProjects[index], newProjects[swapIndex]] = [newProjects[swapIndex], newProjects[index]];

    // Update order values
    const reordered = newProjects.map((p, i) => ({ ...p, order: i }));
    setProjects(reordered);

    // Save to backend
    setReordering(true);
    try {
      await api.post("/api/admin/projects/reorder", {
        projects: reordered.map((p) => ({ id: p.id, order: p.order })),
      });
      toast.success("Order updated");
    } catch {
      toast.error("Reorder failed");
      fetchProjects();
    } finally {
      setReordering(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (editingId) {
        await api.put(`/api/admin/projects/${editingId}`, form);
        toast.success("Project updated");
      } else {
        await api.post("/api/admin/projects", form);
        toast.success("Project created");
      }
      setShowForm(false);
      setEditingId(null);
      setForm(emptyForm);
      fetchProjects();
    } catch {
      toast.error("Operation failed");
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (project: Project) => {
    setForm({
      name: project.name,
      description: project.description,
      tech_stack: project.tech_stack,
      repo_url: project.repo_url || "",
      demo_url: project.demo_url || "",
      image_url: project.image_url || "",
      order: project.order,
    });
    setEditingId(project.id);
    setShowForm(true);
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this project?")) return;
    try {
      await api.delete(`/api/admin/projects/${id}`);
      toast.success("Project deleted");
      fetchProjects();
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
        <h1 className="text-2xl font-bold text-foreground">Projects</h1>
        <button
          onClick={() => {
            setForm(emptyForm);
            setEditingId(null);
            setShowForm(true);
          }}
          className="inline-flex items-center gap-2 px-3 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Plus size={16} />
          Add Project
        </button>
      </div>

      {/* Display count setting */}
      <div className="mb-6 bg-surface border border-border rounded-lg p-4">
        <div className="flex items-center gap-4">
          <label className="text-sm text-muted whitespace-nowrap">
            Projects to display on homepage:
          </label>
          <input
            type="number"
            min={1}
            value={displayCount}
            onChange={(e) => setDisplayCount(parseInt(e.target.value) || 6)}
            className="w-20 bg-background border border-border rounded-lg px-3 py-1.5 text-sm text-foreground focus:outline-none focus:border-primary"
          />
          <button
            onClick={handleDisplayCountSave}
            className="inline-flex items-center gap-1 px-3 py-1.5 bg-primary hover:bg-primary-hover text-white rounded-lg text-xs font-medium transition-colors"
          >
            <Save size={12} />
            Save
          </button>
        </div>
      </div>

      {/* Form modal */}
      {showForm && (
        <div className="mb-6 bg-surface border border-border rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-foreground">
              {editingId ? "Edit Project" : "New Project"}
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
                <label className="block text-sm text-muted mb-1">Name</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-muted mb-1">
                  Tech Stack (comma-separated)
                </label>
                <input
                  type="text"
                  value={form.tech_stack}
                  onChange={(e) =>
                    setForm({ ...form, tech_stack: e.target.value })
                  }
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                />
              </div>
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
                Project Image
              </label>
              <div className="flex items-center gap-3">
                {form.image_url && (
                  <div className="w-16 h-16 rounded-lg overflow-hidden border border-border flex-shrink-0">
                    <img
                      src={form.image_url.startsWith("/uploads/") ? `${API_BASE_URL}${form.image_url}` : form.image_url}
                      alt="Project preview"
                      className="w-full h-full object-cover"
                    />
                  </div>
                )}
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  onChange={handleImageUpload}
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
                  {form.image_url ? "Change Image" : "Upload Image"}
                </button>
                {form.image_url && (
                  <button
                    type="button"
                    onClick={() => setForm({ ...form, image_url: "" })}
                    className="text-xs text-muted hover:text-red-400 transition-colors"
                  >
                    Remove
                  </button>
                )}
              </div>
            </div>
            <div className="grid sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm text-muted mb-1">
                  Repo URL
                </label>
                <input
                  type="url"
                  value={form.repo_url}
                  onChange={(e) =>
                    setForm({ ...form, repo_url: e.target.value })
                  }
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                />
              </div>
              <div>
                <label className="block text-sm text-muted mb-1">
                  Demo URL
                </label>
                <input
                  type="url"
                  value={form.demo_url}
                  onChange={(e) =>
                    setForm({ ...form, demo_url: e.target.value })
                  }
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                />
              </div>
              <div>
                <label className="block text-sm text-muted mb-1">Order</label>
                <input
                  type="number"
                  value={form.order}
                  onChange={(e) =>
                    setForm({ ...form, order: parseInt(e.target.value) || 0 })
                  }
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                />
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

      {/* Project list with reorder buttons */}
      <div className="space-y-3">
        {projects.map((project, index) => (
          <div
            key={project.id}
            className="bg-surface border border-border rounded-lg p-4 flex items-center justify-between"
          >
            <div className="flex items-center gap-3">
              <div className="flex flex-col gap-0.5">
                <button
                  onClick={() => moveProject(index, "up")}
                  disabled={index === 0 || reordering}
                  className="p-1 text-muted hover:text-foreground transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                  aria-label="Move up"
                >
                  <ArrowUp size={14} />
                </button>
                <button
                  onClick={() => moveProject(index, "down")}
                  disabled={index === projects.length - 1 || reordering}
                  className="p-1 text-muted hover:text-foreground transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                  aria-label="Move down"
                >
                  <ArrowDown size={14} />
                </button>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-foreground">
                  {project.name}
                </h3>
                <p className="text-xs text-muted mt-1">{project.tech_stack}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted mr-2">#{project.order}</span>
              <button
                onClick={() => handleEdit(project)}
                className="p-2 text-muted hover:text-foreground transition-colors"
                aria-label="Edit"
              >
                <Pencil size={14} />
              </button>
              <button
                onClick={() => handleDelete(project.id)}
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
