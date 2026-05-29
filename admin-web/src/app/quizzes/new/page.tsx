"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createQuiz } from "@/lib/api";
import { useRouter } from "next/navigation";
import toast from "react-hot-toast";
import QuizSetForm from "@/components/QuizSetForm";

export default function NewQuizPage() {
  const router = useRouter();
  const qc = useQueryClient();

  const { mutateAsync, isPending } = useMutation({
    mutationFn: createQuiz,
    onSuccess: (q) => {
      qc.invalidateQueries({ queryKey: ["quizzes"] });
      toast.success("Quiz created!");
      router.push(`/quizzes/${q.id}`);
    },
    onError: () => toast.error("Failed to create quiz"),
  });

  return (
    <div className="max-w-xl">
      <h1 className="text-2xl font-bold mb-6">New Quiz</h1>
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <QuizSetForm
          onSubmit={mutateAsync}
          isLoading={isPending}
          submitLabel="Create Quiz"
        />
      </div>
    </div>
  );
}
