"use client";

import { useQuery } from "@tanstack/react-query";
import { getQuizSets, getSessions } from "@/lib/api";
import { BookOpen, CheckCircle, FileQuestion, Users } from "lucide-react";

export default function DashboardPage() {
  const { data: quizSets = [] } = useQuery({
    queryKey: ["quiz-sets"],
    queryFn: getQuizSets,
  });

  const { data: sessions = [] } = useQuery({
    queryKey: ["sessions"],
    queryFn: getSessions,
  });

  const published = quizSets.filter((q) => q.is_published).length;
  const totalQuestions = 0; // populated per quiz set fetch

  const stats = [
    { label: "Quiz Sets", value: quizSets.length, icon: BookOpen, color: "bg-blue-50 text-blue-600" },
    { label: "Published", value: published, icon: CheckCircle, color: "bg-green-50 text-green-600" },
    { label: "Sessions", value: sessions.length, icon: Users, color: "bg-purple-50 text-purple-600" },
    { label: "Questions", value: totalQuestions, icon: FileQuestion, color: "bg-orange-50 text-orange-600" },
  ];

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {stats.map((s) => (
          <div key={s.label} className="bg-white rounded-xl border border-gray-200 p-5">
            <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${s.color} mb-3`}>
              <s.icon className="w-5 h-5" />
            </div>
            <p className="text-2xl font-bold">{s.value}</p>
            <p className="text-sm text-gray-500">{s.label}</p>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h2 className="font-semibold mb-4">Recent Quiz Sets</h2>
        {quizSets.length === 0 ? (
          <p className="text-gray-400 text-sm">No quiz sets yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-100">
                <th className="pb-2">Title</th>
                <th className="pb-2">Category</th>
                <th className="pb-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {quizSets.slice(0, 5).map((qs) => (
                <tr key={qs.id} className="border-b border-gray-50 last:border-0">
                  <td className="py-2 font-medium">{qs.title}</td>
                  <td className="py-2">
                    <span className="px-2 py-0.5 rounded bg-gray-100 text-xs">
                      {qs.category}
                    </span>
                  </td>
                  <td className="py-2">
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-medium ${
                        qs.is_published
                          ? "bg-green-100 text-green-700"
                          : "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {qs.is_published ? "Published" : "Draft"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
