"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteQuestion,
  getQuestions,
  getQuizzes,
  togglePublish,
  updateQuiz,
} from "@/lib/api";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import toast from "react-hot-toast";
import { ArrowLeft, Eye, EyeOff, Plus, Trash2, Pencil } from "lucide-react";
import QuizSetForm from "@/components/QuizSetForm";
import type { Question } from "@/types";

export default function EditQuizPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const router = useRouter();

  const { data: quizzes = [] } = useQuery({
    queryKey: ["quizzes"],
    queryFn: getQuizzes,
  });
  const quiz = quizzes.find((q) => q.id === id);

  const { data: questions = [], isLoading: qLoading } = useQuery({
    queryKey: ["questions", id],
    queryFn: () => getQuestions(id),
    enabled: !!id,
  });

  const updateMut = useMutation({
    mutationFn: (data: Parameters<typeof updateQuiz>[1]) =>
      updateQuiz(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["quizzes"] });
      toast.success("Saved");
    },
    onError: () => toast.error("Failed to save"),
  });

  const toggleMut = useMutation({
    mutationFn: () => togglePublish(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["quizzes"] }),
  });

  const deleteQMut = useMutation({
    mutationFn: (qid: string) => deleteQuestion(qid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["questions", id] });
      toast.success("Question deleted");
    },
  });

  const handleDeleteQ = (q: Question) => {
    if (!confirm(`Delete question "${q.content.slice(0, 60)}..."?`)) return;
    deleteQMut.mutate(q.id);
  };

  if (!quiz) return <p className="text-gray-400">Loading...</p>;

  return (
    <div className="max-w-3xl">
      <div className="flex items-center gap-3 mb-6">
        <Link href="/quizzes" className="p-1.5 rounded hover:bg-gray-100">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <h1 className="text-2xl font-bold flex-1">{quiz.title}</h1>
        <button
          onClick={() => toggleMut.mutate()}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
            quiz.is_published
              ? "border-gray-300 text-gray-600 hover:bg-gray-50"
              : "border-green-500 text-green-700 hover:bg-green-50"
          }`}
        >
          {quiz.is_published ? (
            <>
              <EyeOff className="w-4 h-4" /> Unpublish
            </>
          ) : (
            <>
              <Eye className="w-4 h-4" /> Publish
            </>
          )}
        </button>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
        <h2 className="font-semibold mb-4">Details</h2>
        <QuizSetForm
          defaultValues={quiz}
          onSubmit={updateMut.mutateAsync}
          isLoading={updateMut.isPending}
        />
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold">
            Questions{" "}
            <span className="text-gray-400 font-normal">
              ({questions.length})
            </span>
          </h2>
          <Link
            href={`/quizzes/${id}/questions/new`}
            className="flex items-center gap-2 bg-brand-600 text-white px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-brand-700"
          >
            <Plus className="w-4 h-4" /> Add Question
          </Link>
        </div>

        {qLoading ? (
          <p className="text-gray-400 text-sm">Loading questions...</p>
        ) : questions.length === 0 ? (
          <p className="text-gray-400 text-sm">No questions yet.</p>
        ) : (
          <ol className="space-y-2">
            {questions.map((q, i) => (
              <li
                key={q.id}
                className="flex items-start gap-3 border border-gray-100 rounded-lg p-3 hover:bg-gray-50"
              >
                <span className="text-gray-400 text-sm font-mono w-6 shrink-0 pt-0.5">
                  {i + 1}.
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium line-clamp-2">
                    {q.content}
                  </p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs px-1.5 py-0.5 bg-gray-100 rounded text-gray-500">
                      {q.type}
                    </span>
                    <span className="text-xs text-gray-400">
                      {q.options?.length ?? 0} options
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <Link
                    href={`/quizzes/${id}/questions/${q.id}`}
                    className="p-1.5 rounded hover:bg-gray-100 text-gray-500"
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </Link>
                  <button
                    onClick={() => handleDeleteQ(q)}
                    className="p-1.5 rounded hover:bg-red-50 text-gray-500 hover:text-red-600"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
