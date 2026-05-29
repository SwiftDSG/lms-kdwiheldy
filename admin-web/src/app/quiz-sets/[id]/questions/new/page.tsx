"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createQuestion, getQuizSets } from "@/lib/api";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import toast from "react-hot-toast";
import QuestionEditor from "@/components/QuestionEditor";

export default function NewQuestionPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();

  const { data: quizSets = [] } = useQuery({
    queryKey: ["quiz-sets"],
    queryFn: getQuizSets,
  });
  const quizSet = quizSets.find((q) => q.id === id);

  const { mutateAsync, isPending } = useMutation({
    mutationFn: createQuestion,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["questions", id] });
      toast.success("Question added!");
      router.push(`/quiz-sets/${id}`);
    },
    onError: () => toast.error("Failed to add question"),
  });

  return (
    <div className="max-w-2xl">
      <div className="flex items-center gap-3 mb-6">
        <Link href={`/quiz-sets/${id}`} className="p-1.5 rounded hover:bg-gray-100">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <h1 className="text-2xl font-bold">New Question</h1>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <QuestionEditor
          quizSetId={id}
          category={quizSet?.category}
          onSubmit={mutateAsync}
          isLoading={isPending}
          submitLabel="Add Question"
        />
      </div>
    </div>
  );
}
