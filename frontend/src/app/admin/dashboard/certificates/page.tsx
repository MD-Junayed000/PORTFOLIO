"use client";

import { useEffect, useState, useRef } from "react";
import { Plus, Pencil, Trash2, Loader2, X, Upload, FileText } from "lucide-react";
import api from "@/lib/api";
import toast from "react-hot-toast";
import type { Certificate } from "@/types";

interface CertificateForm {
  name: string;
  issuer: string;
  date: string;
  file_path: string;
  // Cloudinary public_id of the uploaded file. Captured from
  // /api/admin/upload-certificate so the backend can re-sign the URL
  // on the public proxy without having to regex-parse the secure_url.
  file_public_id: string;
}

const emptyForm: CertificateForm = {
  name: "",
  issuer: "",
  date: "",
  file_path: "",
  file_public_id: "",
};

export default function AdminCertificates() {
  const [certificates, setCertificates] = useState<Certificate[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<CertificateForm>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await api.post("/api/admin/upload-certificate", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setForm({
        ...form,
        file_path: res.data.file_url,
        // Persist the Cloudinary public_id alongside the secure_url so the
        // public proxy endpoint can sign a download URL for the file.
        file_public_id: res.data.public_id || "",
      });
      toast.success("File uploaded");
    } catch {
      toast.error("Upload failed");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const fetchCertificates = () => {
    api
      .get("/api/admin/certificates")
      .then((res) => setCertificates(res.data))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchCertificates();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        name: form.name,
        issuer: form.issuer,
        date: form.date,
        file_path: form.file_path || null,
        file_public_id: form.file_public_id || null,
      };
      if (editingId) {
        await api.put(`/api/admin/certificates/${editingId}`, payload);
        toast.success("Certificate updated");
      } else {
        await api.post("/api/admin/certificates", payload);
        toast.success("Certificate created");
      }
      setShowForm(false);
      setEditingId(null);
      setForm(emptyForm);
      fetchCertificates();
    } catch {
      toast.error("Operation failed");
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (cert: Certificate) => {
    setForm({
      name: cert.name,
      issuer: cert.issuer,
      date: cert.date,
      file_path: cert.file_path || "",
      file_public_id: cert.file_public_id || "",
    });
    setEditingId(cert.id);
    setShowForm(true);
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this certificate?")) return;
    try {
      await api.delete(`/api/admin/certificates/${id}`);
      toast.success("Certificate deleted");
      fetchCertificates();
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
        <h1 className="text-2xl font-bold text-foreground">Certificates</h1>
        <button
          onClick={() => {
            setForm(emptyForm);
            setEditingId(null);
            setShowForm(true);
          }}
          className="inline-flex items-center gap-2 px-3 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Plus size={16} />
          Add Certificate
        </button>
      </div>

      {showForm && (
        <div className="mb-6 bg-surface border border-border rounded-lg p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-foreground">
              {editingId ? "Edit Certificate" : "New Certificate"}
            </h2>
            <button
              onClick={() => setShowForm(false)}
              className="text-muted hover:text-foreground"
            >
              <X size={18} />
            </button>
          </div>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid sm:grid-cols-3 gap-4">
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
                <label className="block text-sm text-muted mb-1">Issuer</label>
                <input
                  type="text"
                  value={form.issuer}
                  onChange={(e) => setForm({ ...form, issuer: e.target.value })}
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-muted mb-1">Date</label>
                <input
                  type="text"
                  value={form.date}
                  onChange={(e) => setForm({ ...form, date: e.target.value })}
                  className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                  placeholder="e.g. 2024-01"
                  required
                />
              </div>
            </div>
            <div>
              <label className="block text-sm text-muted mb-1">
                Certificate File (jpg/pdf)
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={form.file_path}
                  onChange={(e) => setForm({ ...form, file_path: e.target.value })}
                  className="flex-1 bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
                  placeholder="Upload or paste URL..."
                />
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*,.pdf"
                  onChange={handleFileUpload}
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

      <div className="space-y-3">
        {certificates.map((cert) => (
          <div
            key={cert.id}
            className="bg-surface border border-border rounded-lg p-4 flex items-center justify-between"
          >
            <div className="flex items-center gap-3">
              {cert.file_path && (
                <FileText size={16} className="text-primary flex-shrink-0" />
              )}
              <div>
                <h3 className="text-sm font-semibold text-foreground">
                  {cert.name}
                </h3>
                <p className="text-xs text-muted mt-1">
                  {cert.issuer} - {cert.date}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => handleEdit(cert)}
                className="p-2 text-muted hover:text-foreground transition-colors"
                aria-label="Edit"
              >
                <Pencil size={14} />
              </button>
              <button
                onClick={() => handleDelete(cert.id)}
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
