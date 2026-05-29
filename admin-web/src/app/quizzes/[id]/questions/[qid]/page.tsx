"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getQuestion, getQuizzes, updateQuestion } from "@/lib/api";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import toast from "react-hot-toast";
import QuestionEditor from "@/components/QuestionEditor";

export default function EditQuestionPage() {
  const { id, qid } = useParams<{ id: string; qid: string }>();
  const router = useRouter();
  const qc = useQueryClient();

  const { data: quizzes = [] } = useQuery({
    queryKey: ["quizzes"],
    queryFn: getQuizzes,
  });
  const quiz = quizzes.find((q) => q.id === id);

  const { data: question, isError: qError } = useQuery({
    queryKey: ["question", qid],
    queryFn: () => getQuestion(qid),
  });

  const { mutateAsync, isPending } = useMutation({
    mutationFn: (data: Parameters<typeof updateQuestion>[1]) =>
      updateQuestion(qid, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["questions", id] });
      toast.success("Saved!");
      router.push(`/quizzes/${id}`);
    },
    onError: () => toast.error("Failed to save"),
  });

  if (qError) return <p className="text-red-500">Failed to load question. Is the server running?</p>;
  if (!question) return <p className="text-gray-400">Loading...</p>;

  return (
    <div className="max-w-2xl">
      <div className="flex items-center gap-3 mb-6">
        <Link href={`/quizzes/${id}`} className="p-1.5 rounded hover:bg-gray-100">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <h1 className="text-2xl font-bold">Edit Question</h1>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <QuestionEditor
          quizId={id}
          defaultValues={question}
          category={quiz?.category}
          onSubmit={mutateAsync}
          isLoading={isPending}
        />
      </div>
    </div>
  );
}
