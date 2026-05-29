"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createQuizSet } from "@/lib/api";
import { useRouter } from "next/navigation";
import toast from "react-hot-toast";
import QuizSetForm from "@/components/QuizSetForm";

export default function NewQuizSetPage() {
  const router = useRouter();
  const qc = useQueryClient();

  const { mutateAsync, isPending } = useMutation({
    mutationFn: createQuizSet,
    onSuccess: (qs) => {
      qc.invalidateQueries({ queryKey: ["quiz-sets"] });
      toast.success("Quiz set created!");
      router.push(`/quiz-sets/${qs.id}`);
    },
    onError: () => toast.error("Failed to create quiz set"),
  });

  return (
    <div className="max-w-xl">
      <h1 className="text-2xl font-bold mb-6">New Quiz Set</h1>
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <QuizSetForm
          onSubmit={mutateAsync}
          isLoading={isPending}
          submitLabel="Create Quiz Set"
        />
      </div>
    </div>
  );
}
