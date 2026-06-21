"use client";

import { useEffect, useState } from "react";
import { Loader2, CheckCircle, XCircle, Trash2, Zap, Clock } from "lucide-react";
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

  // Smoke test state
  const [smokeLoading, setSmokeLoading] = useState(false);
  const [smokeResult, setSmokeResult] = useState<{
    status: string;
    response?: string;
    sources?: string[];
    used_hf_api?: boolean;
    model?: string;
    response_time_ms?: number;
    error?: string;
  } | null>(null);

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

  const handleSmokeTest = async () => {
    setSmokeLoading(true);
    setSmokeResult(null);
    try {
      const res = await api.post("/api/admin/settings/smoke-test", null, {
        timeout: 60000,
      });
      setSmokeResult(res.data);
    } catch (err: unknown) {
      const errorMsg =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data
              ?.detail || "Smoke test request failed"
          : "Smoke test request failed";
      setSmokeResult({ status: "failed", error: errorMsg });
    } finally {
      setSmokeLoading(false);
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

      {/* Smoke Test Section */}
      <div className="max-w-xl mt-8">
        <div className="bg-surface border border-border rounded-lg p-6 space-y-4">
          <h2 className="text-lg font-semibold text-foreground">
            API Smoke Test
          </h2>
          <p className="text-sm text-muted">
            Send a test question to verify the chatbot pipeline is working
            end-to-end (HF token, model, and RAG retrieval).
          </p>

          <button
            type="button"
            onClick={handleSmokeTest}
            disabled={smokeLoading}
            className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
          >
            {smokeLoading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Zap size={14} />
            )}
            {smokeLoading ? "Running Smoke Test..." : "Run Smoke Test"}
          </button>

          {smokeResult && (
            <div className="border border-border rounded-lg p-4 space-y-3 bg-background">
              {/* Status */}
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-muted">Status:</span>
                {smokeResult.status === "success" ? (
                  <span className="inline-flex items-center gap-1 text-sm font-semibold text-green-600">
                    <CheckCircle size={14} />
                    SUCCESS
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-sm font-semibold text-red-500">
                    <XCircle size={14} />
                    FAILED
                  </span>
                )}
              </div>

              {/* Response mode */}
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-muted">
                  Response mode:
                </span>
                <span className="text-sm text-foreground">
                  {smokeResult.used_hf_api
                    ? "HuggingFace API"
                    : "Fallback (no API)"}
                </span>
              </div>

              {/* Model */}
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-muted">Model:</span>
                <span className="text-sm text-foreground font-mono">
                  {smokeResult.model || "N/A"}
                </span>
              </div>

              {/* Response time */}
              {smokeResult.response_time_ms !== undefined && (
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-muted">
                    Response time:
                  </span>
                  <span className="inline-flex items-center gap-1 text-sm text-foreground">
                    <Clock size={12} />
                    {smokeResult.response_time_ms} ms
                  </span>
                </div>
              )}

              {/* Generated answer */}
              {smokeResult.response && (
                <div>
                  <span className="text-sm font-medium text-muted block mb-1">
                    Generated answer:
                  </span>
                  <div className="bg-surface border border-border rounded p-3 max-h-48 overflow-y-auto">
                    <p className="text-sm text-foreground whitespace-pre-wrap">
                      {smokeResult.response}
                    </p>
                  </div>
                </div>
              )}

              {/* Sources */}
              {smokeResult.sources && smokeResult.sources.length > 0 && (
                <div>
                  <span className="text-sm font-medium text-muted block mb-1">
                    Sources:
                  </span>
                  <div className="flex flex-wrap gap-1">
                    {smokeResult.sources.map((source, i) => (
                      <span
                        key={i}
                        className="text-xs px-2 py-0.5 bg-surface border border-border rounded text-muted"
                      >
                        {source}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Error */}
              {smokeResult.error && (
                <div>
                  <span className="text-sm font-medium text-red-500 block mb-1">
                    Error:
                  </span>
                  <div className="bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-800 rounded p-3">
                    <p className="text-sm text-red-700 dark:text-red-400">
                      {smokeResult.error}
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
