"use client";

import { useEffect, useState } from "react";
import { Upload, Trash2, Loader2, FileText, Pencil, X, Check } from "lucide-react";
import api from "@/lib/api";
import toast from "react-hot-toast";
import type { Document } from "@/types";

export default function AdminDocuments() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [topicName, setTopicName] = useState("");
  const [editingTopicId, setEditingTopicId] = useState<number | null>(null);
  const [editTopicValue, setEditTopicValue] = useState("");

  const fetchDocuments = () => {
    api
      .get("/api/admin/documents")
      .then((res) => setDocuments(res.data))
      .catch(() => setDocuments([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchDocuments();
  }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);
    if (topicName.trim()) {
      formData.append("topic_name", topicName.trim());
    }
    setUploading(true);

    try {
      await api.post("/api/admin/upload-pdf", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success("PDF uploaded and processed");
      setTopicName("");
      fetchDocuments();
    } catch {
      toast.error("Upload failed");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this document? It will be removed from the vector database.")) return;
    try {
      await api.delete(`/api/admin/documents/${id}`);
      toast.success("Document deleted");
      fetchDocuments();
    } catch {
      toast.error("Delete failed");
    }
  };

  const handleEditTopic = (doc: Document) => {
    setEditingTopicId(doc.id);
    setEditTopicValue(doc.topic || "");
  };

  const handleSaveTopic = async (id: number) => {
    try {
      await api.put(`/api/admin/documents/${id}`, { topic: editTopicValue });
      toast.success("Topic updated");
      setEditingTopicId(null);
      fetchDocuments();
    } catch {
      toast.error("Failed to update topic");
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
        <h1 className="text-2xl font-bold text-foreground">
          Documents (RAG Knowledge Base)
        </h1>
      </div>

      <div className="mb-6 bg-surface border border-border rounded-lg p-6">
        <p className="text-sm text-muted mb-4">
          Upload PDF documents to add them to the chatbot knowledge base. The content
          will be processed and stored in the vector database for RAG retrieval.
        </p>
        <div className="flex flex-col sm:flex-row items-start sm:items-end gap-3">
          <div>
            <label className="block text-sm text-muted mb-1">
              Topic Name (optional)
            </label>
            <input
              type="text"
              value={topicName}
              onChange={(e) => setTopicName(e.target.value)}
              placeholder="e.g., Resume, Research Paper"
              className="w-full sm:w-64 bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
            />
          </div>
          <label className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-sm font-medium transition-colors cursor-pointer">
            {uploading ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Upload size={16} />
            )}
            {uploading ? "Processing..." : "Upload PDF"}
            <input
              type="file"
              accept=".pdf"
              onChange={handleUpload}
              className="hidden"
              disabled={uploading}
            />
          </label>
        </div>
      </div>

      <div className="space-y-3">
        {documents.length === 0 && (
          <p className="text-sm text-muted text-center py-8">
            No documents uploaded yet.
          </p>
        )}
        {documents.map((doc) => (
          <div
            key={doc.id}
            className="bg-surface border border-border rounded-lg p-4 flex items-center justify-between"
          >
            <div className="flex items-center gap-3 flex-1 min-w-0">
              <FileText size={18} className="text-primary flex-shrink-0" />
              <div className="min-w-0">
                <h3 className="text-sm font-semibold text-foreground truncate">
                  {doc.original_name || doc.filename}
                </h3>
                <div className="flex items-center gap-2 mt-1">
                  {editingTopicId === doc.id ? (
                    <div className="flex items-center gap-1">
                      <input
                        type="text"
                        value={editTopicValue}
                        onChange={(e) => setEditTopicValue(e.target.value)}
                        className="bg-background border border-border rounded px-2 py-0.5 text-xs text-foreground focus:outline-none focus:border-primary"
                        placeholder="Topic name"
                        autoFocus
                      />
                      <button
                        onClick={() => handleSaveTopic(doc.id)}
                        className="p-1 text-green-600 hover:text-green-500"
                      >
                        <Check size={12} />
                      </button>
                      <button
                        onClick={() => setEditingTopicId(null)}
                        className="p-1 text-muted hover:text-foreground"
                      >
                        <X size={12} />
                      </button>
                    </div>
                  ) : (
                    <>
                      {doc.topic && (
                        <span className="text-xs bg-primary/10 text-primary px-2 py-0.5 rounded">
                          {doc.topic}
                        </span>
                      )}
                      <button
                        onClick={() => handleEditTopic(doc)}
                        className="p-1 text-muted hover:text-foreground transition-colors"
                        aria-label="Edit topic"
                      >
                        <Pencil size={11} />
                      </button>
                    </>
                  )}
                  <span className="text-xs text-muted">{doc.uploaded_at}</span>
                  {doc.chunk_count != null && (
                    <span className="text-xs text-muted">
                      ({doc.chunk_count} chunks)
                    </span>
                  )}
                </div>
              </div>
            </div>
            <button
              onClick={() => handleDelete(doc.id)}
              className="p-2 text-muted hover:text-red-400 transition-colors flex-shrink-0"
              aria-label="Delete"
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
