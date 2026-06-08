"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteQuiz, getQuizzes, togglePublish } from "@/lib/api";
import Link from "next/link";
import { Plus, Pencil, Trash2, Eye, EyeOff } from "lucide-react";
import toast from "react-hot-toast";
import type { Quiz } from "@/types";

export default function QuizSetsPage() {
  const qc = useQueryClient();
  const { data: quizSets = [], isLoading } = useQuery({
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

  const handleDelete = (qs: Quiz) => {
    if (!confirm(`Delete "${qs.title}"? This cannot be undone.`)) return;
    deleteMut.mutate(qs.id);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Quiz Sets</h1>
        <Link
          href="/quiz-sets/new"
          className="flex items-center gap-2 bg-brand-600 text-white px-4 py-2 rounded-md text-sm font-semibold hover:bg-brand-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Quiz Set
        </Link>
      </div>

      {isLoading ? (
        <p className="text-gray-400">Loading...</p>
      ) : quizSets.length === 0 ? (
        <div className="bg-white rounded-xl border-3 border-brand-600 p-12 text-center text-gray-400">
          <p className="text-lg mb-2">No quiz sets yet</p>
          <p className="text-sm">Create your first quiz set to get started.</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border-3 border-brand-600 overflow-hidden">
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
              {quizSets.map((qs) => (
                <tr key={qs.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium">{qs.title}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded bg-brand-50 text-brand-600 text-xs font-semibold">
                      {qs.category}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {qs.time_limit ? `${qs.time_limit} min` : "—"}
                  </td>
                  <td className="px-4 py-3">
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
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Link
                        href={`/quiz-sets/${qs.id}`}
                        className="p-1.5 border-3 border-brand-600 rounded-md text-brand-600 hover:bg-brand-50"
                        title="Edit"
                      >
                        <Pencil className="w-4 h-4" />
                      </Link>
                      <button
                        onClick={() => toggleMut.mutate(qs.id)}
                        className="p-1.5 border-3 border-brand-600 rounded-md text-brand-600 hover:bg-brand-50"
                        title={qs.is_published ? "Unpublish" : "Publish"}
                      >
                        {qs.is_published ? (
                          <EyeOff className="w-4 h-4" />
                        ) : (
                          <Eye className="w-4 h-4" />
                        )}
                      </button>
                      <button
                        onClick={() => handleDelete(qs)}
                        className="p-1.5 border-3 border-danger rounded-md text-danger hover:bg-red-50"
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
