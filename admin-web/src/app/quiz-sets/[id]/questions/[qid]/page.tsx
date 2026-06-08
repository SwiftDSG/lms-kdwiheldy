"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getQuestion, getQuizzes, updateQuestion } from "@/lib/api";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Wand2 } from "lucide-react";
import toast from "react-hot-toast";
import QuestionEditor from "@/components/QuestionEditor";

const NO_GENERATE_SUBTYPES = new Set([
  "ANALOGI_GAMBAR",
  "PELAYANAN_PUBLIK", "PROFESIONALISME", "JEJARING_KERJA", "SOSIAL_BUDAYA",
  "TEKNOLOGI_INFORMASI", "ORIENTASI_BELAJAR", "MENGENDALIKAN_DIRI",
  "BERADAPTASI", "KREATIVITAS_INOVASI",
]);

export default function EditQuestionPage() {
  const { id, qid } = useParams<{ id: string; qid: string }>();
  const router = useRouter();
  const qc = useQueryClient();

  const { data: quizSets = [] } = useQuery({
    queryKey: ["quizzes"],
    queryFn: getQuizzes,
  });
  const quizSet = quizSets.find((q) => q.id === id);

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
      router.push(`/quiz-sets/${id}`);
    },
    onError: () => toast.error("Failed to save"),
  });

  if (qError) return <p className="text-red-500">Failed to load question. Is the server running?</p>;
  if (!question) return <p className="text-gray-400">Loading...</p>;

  return (
    <div className="max-w-2xl">
      <div className="flex items-center gap-3 mb-6">
        <Link href={`/quiz-sets/${id}`} className="p-1.5 border-3 border-brand-600 rounded-md text-brand-600 hover:bg-brand-50">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <h1 className="text-2xl font-bold flex-1">Edit Question</h1>
        {question && !NO_GENERATE_SUBTYPES.has(question.subtype) && (
          <Link
            href={`/quiz-sets/${id}/generate/${qid}`}
            className="flex items-center gap-1.5 px-3 py-1.5 border-3 border-brand-600 rounded-md text-brand-600 hover:bg-brand-50 text-sm font-semibold"
          >
            <Wand2 className="w-4 h-4" />
            Generate Similar
          </Link>
        )}
      </div>

      <div className="bg-white rounded-xl border-3 border-brand-600 p-6">
        <QuestionEditor
          quizId={id}
          defaultValues={question}
          category={quizSet?.category}
          onSubmit={mutateAsync}
          isLoading={isPending}
        />
      </div>
    </div>
  );
}
