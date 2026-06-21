"use client";

import { useEffect, useState } from "react";
import { Loader2, Database } from "lucide-react";
import api from "@/lib/api";
import type { DatabaseInfo } from "@/types";

export default function AdminDatabase() {
  const [tables, setTables] = useState<DatabaseInfo[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get("/api/admin/database")
      .then((res) => setTables(res.data.tables || []))
      .catch(() => setTables([]))
      .finally(() => setLoading(false));
  }, []);

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
        <h1 className="text-2xl font-bold text-foreground">Database</h1>
      </div>

      <div className="bg-surface border border-border rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Database size={16} className="text-primary" />
            <h2 className="text-sm font-semibold text-foreground">
              Tables Overview
            </h2>
          </div>
          <p className="text-xs text-muted mt-1">
            Current database tables and their row counts.
          </p>
        </div>
        <table className="w-full">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left px-6 py-3 text-xs font-medium text-muted uppercase">
                Table Name
              </th>
              <th className="text-right px-6 py-3 text-xs font-medium text-muted uppercase">
                Row Count
              </th>
            </tr>
          </thead>
          <tbody>
            {tables.length === 0 && (
              <tr>
                <td
                  colSpan={2}
                  className="px-6 py-8 text-center text-sm text-muted"
                >
                  No table information available.
                </td>
              </tr>
            )}
            {tables.map((table) => (
              <tr
                key={table.name}
                className="border-b border-border last:border-0"
              >
                <td className="px-6 py-3 text-sm text-foreground font-mono">
                  {table.name}
                </td>
                <td className="px-6 py-3 text-sm text-foreground text-right">
                  {table.row_count}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
