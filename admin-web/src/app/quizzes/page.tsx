"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteQuiz, getQuizzes, togglePublish } from "@/lib/api";
import Link from "next/link";
import { Plus, Pencil, Trash2, Eye, EyeOff } from "lucide-react";
import toast from "react-hot-toast";
import type { Quiz } from "@/types";

export default function QuizzesPage() {
  const qc = useQueryClient();
  const { data: quizzes = [], isLoading } = useQuery({
    queryKey: ["quizzes"],
    queryFn: getQuizzes,
  });

  const toggleMut = useMutation({
    mutationFn: (id: string) => togglePublish(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["quizzes"] });
      toast.success("Status updated");
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteQuiz(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["quizzes"] });
      toast.success("Deleted");
    },
  });

  const handleDelete = (q: Quiz) => {
    if (!confirm(`Delete "${q.title}"? This cannot be undone.`)) return;
    deleteMut.mutate(q.id);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Quizzes</h1>
        <Link
          href="/quizzes/new"
          className="flex items-center gap-2 bg-brand-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-brand-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Quiz
        </Link>
      </div>

      {isLoading ? (
        <p className="text-gray-400">Loading...</p>
      ) : quizzes.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-gray-400">
          <p className="text-lg mb-2">No quizzes yet</p>
          <p className="text-sm">Create your first quiz to get started.</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-left">
              <tr>
                <th className="px-4 py-3 font-medium">Title</th>
                <th className="px-4 py-3 font-medium">Category</th>
                <th className="px-4 py-3 font-medium">Time Limit</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {quizzes.map((q) => (
                <tr key={q.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium">{q.title}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded bg-blue-50 text-blue-700 text-xs font-medium">
                      {q.category}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {q.time_limit ? `${q.time_limit} min` : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-medium ${
                        q.is_published
                          ? "bg-green-100 text-green-700"
                          : "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {q.is_published ? "Published" : "Draft"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Link
                        href={`/quizzes/${q.id}`}
                        className="p-1.5 rounded hover:bg-gray-100 text-gray-500"
                        title="Edit"
                      >
                        <Pencil className="w-4 h-4" />
                      </Link>
                      <button
                        onClick={() => toggleMut.mutate(q.id)}
                        className="p-1.5 rounded hover:bg-gray-100 text-gray-500"
                        title={q.is_published ? "Unpublish" : "Publish"}
                      >
                        {q.is_published ? (
                          <EyeOff className="w-4 h-4" />
                        ) : (
                          <Eye className="w-4 h-4" />
                        )}
                      </button>
                      <button
                        onClick={() => handleDelete(q)}
                        className="p-1.5 rounded hover:bg-red-50 text-gray-500 hover:text-red-600"
                        title="Delete"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
