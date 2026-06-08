"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createQuiz } from "@/lib/api";
import { useRouter } from "next/navigation";
import toast from "react-hot-toast";
import QuizSetForm from "@/components/QuizSetForm";

export default function NewQuizSetPage() {
  const router = useRouter();
  const qc = useQueryClient();

  const { mutateAsync, isPending } = useMutation({
    mutationFn: createQuiz,
    onSuccess: (qs) => {
      qc.invalidateQueries({ queryKey: ["quizzes"] });
      toast.success("Quiz set created!");
      router.push(`/quiz-sets/${qs.id}`);
    },
    onError: () => toast.error("Failed to create quiz set"),
  });

  return (
    <div className="max-w-xl">
      <h1 className="text-2xl font-bold mb-6">New Quiz Set</h1>
      <div className="bg-white rounded-xl border-3 border-brand-600 p-6">
        <QuizSetForm
          onSubmit={mutateAsync}
          isLoading={isPending}
          submitLabel="Create Quiz Set"
        />
      </div>
    </div>
  );
}
