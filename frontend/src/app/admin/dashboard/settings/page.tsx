"use client";

import { useEffect, useState } from "react";
import { Loader2, CheckCircle, XCircle, Trash2 } from "lucide-react";
import api from "@/lib/api";
import toast from "react-hot-toast";

const SUGGESTED_MODELS = [
  "meta-llama/Meta-Llama-3-8B-Instruct",
  "google/gemma-2-9b-it",
  "mistralai/Mistral-7B-Instruct-v0.3",
  "microsoft/Phi-3-mini-4k-instruct",
];

export default function AdminSettings() {
  const [modelId, setModelId] = useState("");
  const [apiToken, setApiToken] = useState("");
  const [tokenSet, setTokenSet] = useState(false);
  const [saving, setSaving] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [loadingSettings, setLoadingSettings] = useState(true);

  useEffect(() => {
    api
      .get("/api/admin/settings")
      .then((res) => {
        setModelId(res.data.hf_model_id || "");
        setTokenSet(res.data.hf_token_set || false);
      })
      .catch(() => {})
      .finally(() => setLoadingSettings(false));
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.put("/api/admin/settings", {
        hf_model_id: modelId,
        hf_api_token: apiToken || undefined,
      });
      toast.success("Settings saved");
      if (apiToken) setTokenSet(true);
      setApiToken("");
    } catch {
      toast.error("Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const handleVerifyToken = async () => {
    setVerifying(true);
    try {
      const res = await api.post("/api/admin/settings/verify-token");
      if (res.data.valid) {
        toast.success(res.data.detail || "Token is valid");
      } else {
        toast.error(res.data.detail || "Token is invalid");
      }
    } catch {
      toast.error("Failed to verify token");
    } finally {
      setVerifying(false);
    }
  };

  const handleRemoveToken = async () => {
    if (!confirm("Remove the stored API token?")) return;
    setRemoving(true);
    try {
      await api.delete("/api/admin/settings/token");
      toast.success("Token removed");
      setTokenSet(false);
    } catch {
      toast.error("Failed to remove token");
    } finally {
      setRemoving(false);
    }
  };

  if (loadingSettings) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 size={24} className="animate-spin text-muted" />
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-foreground mb-6">Settings</h1>

      <form onSubmit={handleSave} className="max-w-xl space-y-6">
        <div className="bg-surface border border-border rounded-lg p-6 space-y-4">
          <h2 className="text-lg font-semibold text-foreground">
            HuggingFace Configuration
          </h2>
          <p className="text-sm text-muted">
            Configure the language model used by the chatbot for generating
            responses.
          </p>

          <div>
            <label
              htmlFor="modelId"
              className="block text-sm text-muted mb-1"
            >
              Model ID
            </label>
            <input
              id="modelId"
              type="text"
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
              placeholder="mistralai/Mistral-7B-Instruct-v0.3"
            />
            <div className="mt-2">
              <p className="text-xs text-muted mb-1">Suggested models:</p>
              <div className="flex flex-wrap gap-1">
                {SUGGESTED_MODELS.map((model) => (
                  <button
                    key={model}
                    type="button"
                    onClick={() => setModelId(model)}
                    className={`text-xs px-2 py-1 rounded border transition-colors ${
                      modelId === model
                        ? "bg-primary text-white border-primary"
                        : "bg-background border-border text-muted hover:text-foreground hover:border-primary"
                    }`}
                  >
                    {model.split("/")[1]}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div>
            <label
              htmlFor="apiToken"
              className="block text-sm text-muted mb-1"
            >
              API Token (leave blank to keep existing)
            </label>
            <input
              id="apiToken"
              type="password"
              value={apiToken}
              onChange={(e) => setApiToken(e.target.value)}
              className="w-full bg-background border border-border rounded-lg px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary"
              placeholder="hf_..."
            />
            {tokenSet && (
              <p className="text-xs text-green-600 mt-1 flex items-center gap-1">
                <CheckCircle size={12} />
                Token is currently set
              </p>
            )}
            {!tokenSet && (
              <p className="text-xs text-muted mt-1 flex items-center gap-1">
                <XCircle size={12} />
                No token stored
              </p>
            )}
          </div>

          {/* Token actions */}
          <div className="flex items-center gap-2 pt-2">
            <button
              type="button"
              onClick={handleVerifyToken}
              disabled={verifying || !tokenSet}
              className="inline-flex items-center gap-2 px-3 py-1.5 bg-background border border-border hover:border-primary text-sm text-foreground rounded-lg transition-colors disabled:opacity-50"
            >
              {verifying ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <CheckCircle size={14} />
              )}
              Verify Token
            </button>
            <button
              type="button"
              onClick={handleRemoveToken}
              disabled={removing || !tokenSet}
              className="inline-flex items-center gap-2 px-3 py-1.5 bg-background border border-border hover:border-red-400 text-sm text-muted hover:text-red-400 rounded-lg transition-colors disabled:opacity-50"
            >
              {removing ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Trash2 size={14} />
              )}
              Remove Token
            </button>
          </div>
        </div>

        <button
          type="submit"
          disabled={saving}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
        >
          {saving && <Loader2 size={14} className="animate-spin" />}
          Save Settings
        </button>
      </form>
    </div>
  );
}
