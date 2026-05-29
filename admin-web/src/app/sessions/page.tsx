"use client";

import { useQuery } from "@tanstack/react-query";
import { getQuizSets, getSessions } from "@/lib/api";

export default function SessionsPage() {
  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ["sessions"],
    queryFn: getSessions,
  });

  const { data: quizSets = [] } = useQuery({
    queryKey: ["quiz-sets"],
    queryFn: getQuizSets,
  });

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Sessions</h1>

      {isLoading ? (
        <p className="text-gray-400">Loading...</p>
      ) : sessions.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400">
          <p>No sessions yet. Sessions are submitted from the iPad app.</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-left">
              <tr>
                <th className="px-4 py-3 font-medium">Quiz Set</th>
                <th className="px-4 py-3 font-medium">Device</th>
                <th className="px-4 py-3 font-medium">Score</th>
                <th className="px-4 py-3 font-medium">Started</th>
                <th className="px-4 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {sessions.map((s) => {
                const qs = quizSets.find((q) => q.id === s.quiz_set_id);
                return (
                  <tr key={s.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium">
                      {qs?.title ?? s.quiz_set_id}
                    </td>
                    <td className="px-4 py-3 text-gray-400 font-mono text-xs">
                      {s.device_id.slice(0, 8)}…
                    </td>
                    <td className="px-4 py-3 font-bold">
                      {s.score ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {new Date(s.started_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-medium ${
                          s.completed_at
                            ? "bg-green-100 text-green-700"
                            : "bg-yellow-100 text-yellow-700"
                        }`}
                      >
                        {s.completed_at ? "Completed" : "In Progress"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
