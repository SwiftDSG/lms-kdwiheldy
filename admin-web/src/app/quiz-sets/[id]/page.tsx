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
import { ArrowLeft, Eye, EyeOff, Plus, Trash2, Pencil, Wand2 } from "lucide-react";
import QuizSetForm from "@/components/QuizSetForm";
import MathText from "@/components/MathText";
import type { Question } from "@/types";

export default function EditQuizSetPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const router = useRouter();

  const { data: quizSets = [] } = useQuery({
    queryKey: ["quizzes"],
    queryFn: getQuizzes,
  });
  const quizSet = quizSets.find((q) => q.id === id);

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

  if (!quizSet) return <p className="text-gray-400">Loading...</p>;

  return (
    <div className="max-w-3xl">
      <div className="flex items-center gap-3 mb-6">
        <Link href="/quiz-sets" className="p-1.5 border-3 border-brand-600 rounded-md text-brand-600 hover:bg-brand-50">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <h1 className="text-2xl font-bold flex-1">{quizSet.title}</h1>
        <button
          onClick={() => toggleMut.mutate()}
          className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-semibold border-3 transition-colors ${
            quizSet.is_published
              ? "border-brand-600 text-brand-600 hover:bg-brand-50"
              : "border-success text-success hover:bg-green-50"
          }`}
        >
          {quizSet.is_published ? (
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

      {/* Quiz set details form */}
      <div className="bg-white rounded-xl border-3 border-brand-600 p-6 mb-6">
        <h2 className="font-semibold mb-4">Details</h2>
        <QuizSetForm
          defaultValues={quizSet}
          onSubmit={updateMut.mutateAsync}
          isLoading={updateMut.isPending}
        />
      </div>

      {/* Questions */}
      <div className="bg-white rounded-xl border-3 border-brand-600 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold">
            Questions{" "}
            <span className="text-gray-400 font-normal">
              ({questions.length})
            </span>
          </h2>
          <div className="flex gap-2">
            <Link
              href={`/quiz-sets/${id}/generate`}
              className="flex items-center gap-2 border-3 border-brand-600 text-brand-600 px-3 py-1.5 rounded-md text-sm font-semibold hover:bg-brand-50"
            >
              <Wand2 className="w-4 h-4" /> Generate
            </Link>
            <Link
              href={`/quiz-sets/${id}/questions/new`}
              className="flex items-center gap-2 bg-brand-600 text-white px-3 py-1.5 rounded-md text-sm font-semibold hover:bg-brand-700"
            >
              <Plus className="w-4 h-4" /> Add Question
            </Link>
          </div>
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
                className="flex items-start gap-3 border-3 border-brand-600 rounded-xl p-3 hover:bg-brand-50"
              >
                <span className="text-gray-400 text-sm font-mono w-6 shrink-0 pt-0.5">
                  {i + 1}.
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium line-clamp-2">
                    <MathText text={q.content} />
                  </p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-xs px-1.5 py-0.5 bg-brand-50 rounded text-brand-600 font-medium">
                      {q.type}
                    </span>
                    <span className="text-xs text-gray-400">
                      {q.options?.length ?? 0} options
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <Link
                    href={`/quiz-sets/${id}/generate/${q.id}`}
                    className="p-1.5 border-3 border-brand-600 rounded-md text-brand-600 hover:bg-brand-50"
                    title="Generate similar questions"
                  >
                    <Wand2 className="w-3.5 h-3.5" />
                  </Link>
                  <Link
                    href={`/quiz-sets/${id}/questions/${q.id}`}
                    className="p-1.5 border-3 border-brand-600 rounded-md text-brand-600 hover:bg-brand-50"
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </Link>
                  <button
                    onClick={() => handleDeleteQ(q)}
                    className="p-1.5 border-3 border-danger rounded-md text-danger hover:bg-red-50"
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
