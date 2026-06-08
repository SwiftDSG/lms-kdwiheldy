"use client";

import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useEffect } from "react";
import { createQuestion, generateQuestion, getQuestion } from "@/lib/api";
import type { GeneratedQuestion } from "@/types";
import { ArrowLeft, Check, X, Wand2 } from "lucide-react";
import MathText from "@/components/MathText";
import Link from "next/link";
import toast from "react-hot-toast";

export default function GeneratePage() {
  const { id, sourceId } = useParams<{ id: string; sourceId: string }>();
  const qc = useQueryClient();

  const [current, setCurrent] = useState<GeneratedQuestion | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [addedCount, setAddedCount] = useState(0);

  const { data: sourceQuestion } = useQuery({
    queryKey: ["question", sourceId],
    queryFn: () => getQuestion(sourceId),
    enabled: !!sourceId,
  });

  const saveMut = useMutation({
    mutationFn: (q: GeneratedQuestion) =>
      createQuestion({
        quiz_id:     id,
        type:        sourceQuestion?.type ?? "MCQ",
        subtype:     sourceQuestion?.subtype ?? "SILOGISME",
        content:     q.content,
        explanation: q.explanation,
        position:    0,
        options: q.options.map((o) => ({
          label:   o.label,
          content: o.content,
          score:   o.score,
        })),
      }),
    onSuccess: () => {
      setAddedCount((c) => c + 1);
      qc.invalidateQueries({ queryKey: ["questions", id] });
      fetchNext();
    },
    onError: () => toast.error("Failed to save question"),
  });

  const fetchNext = async () => {
    setIsGenerating(true);
    setGenError(null);
    setCurrent(null);
    try {
      const result = await generateQuestion(sourceId);
      setCurrent(result.question);
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Generation failed";
      setGenError(msg);
    } finally {
      setIsGenerating(false);
    }
  };

  // Start generating once source question is loaded
  useEffect(() => {
    if (sourceQuestion) fetchNext();
  }, [sourceQuestion?.id]);

  return (
    <div className="max-w-2xl">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <Link
          href={`/quiz-sets/${id}`}
          className="p-1.5 border-3 border-brand-600 rounded-md text-brand-600 hover:bg-brand-50"
        >
          <ArrowLeft className="w-5 h-5" />
        </Link>
        <h1 className="text-xl font-bold flex-1">Generate Similar Questions</h1>
        {addedCount > 0 && (
          <span className="text-sm text-success font-semibold">
            {addedCount} added
          </span>
        )}
      </div>

      {/* Source question context panel */}
      {sourceQuestion && (
        <div className="bg-brand-50 rounded-xl border-3 border-brand-600 p-4 mb-4">
          <p className="text-xs text-gray-400 font-medium uppercase tracking-wide mb-2">
            Generating similar to
          </p>
          <p className="text-sm font-medium text-gray-700 mb-2">
            <MathText text={sourceQuestion.content} />
          </p>
          <div className="flex flex-wrap gap-1.5">
            {sourceQuestion.options?.map((o) => (
              <span
                key={o.id}
                className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                  o.score === 5
                    ? "bg-green-100 text-green-700"
                    : "bg-brand-100 text-brand-600"
                }`}
              >
                {o.label}. <MathText text={o.content} />
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Generated question card */}
      <div className="bg-white rounded-xl border-3 border-brand-600 p-6 min-h-52 flex flex-col">
        {isGenerating ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-3 text-gray-400">
            <Wand2 className="w-8 h-8 animate-pulse" />
            <p className="text-sm">Generating question...</p>
          </div>
        ) : genError ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-3">
            <p className="text-sm text-red-500">{genError}</p>
            <button
              onClick={fetchNext}
              className="text-sm text-brand-600 hover:underline"
            >
              Try again
            </button>
          </div>
        ) : current ? (
          <>
            <p className="text-sm font-medium mb-4"><MathText text={current.content} /></p>
            <div className="space-y-1.5 mb-6">
              {current.options.map((o) => (
                <div
                  key={o.label}
                  className={`flex items-center gap-2 text-sm px-3 py-1.5 rounded-md border ${
                    o.score === 5
                      ? "bg-green-50 border-green-300 text-green-700 font-semibold"
                      : "border-transparent text-gray-600"
                  }`}
                >
                  <span className="font-mono text-xs w-4 shrink-0">
                    {o.label}.
                  </span>
                  <span className="flex-1"><MathText text={o.content} /></span>
                  {o.score === 5 && (
                    <Check className="w-3.5 h-3.5 shrink-0" />
                  )}
                </div>
              ))}
            </div>
            {(current.explanation || current.tip) && (
              <div className="mb-4 space-y-2 border-t border-gray-100 pt-4">
                {current.explanation && (
                  <div>
                    <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">
                      Explanation
                    </p>
                    <p className="text-sm text-gray-700">
                      <MathText text={current.explanation} />
                    </p>
                  </div>
                )}
                {current.tip && (
                  <div>
                    <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">
                      Tip
                    </p>
                    <p className="text-sm text-gray-600 italic">
                      <MathText text={current.tip} />
                    </p>
                  </div>
                )}
              </div>
            )}
            <div className="flex gap-3 mt-auto">
              <button
                onClick={fetchNext}
                disabled={saveMut.isPending}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-md border-3 border-brand-600 text-brand-600 hover:bg-brand-50 text-sm font-semibold disabled:opacity-50"
              >
                <X className="w-4 h-4" /> Skip
              </button>
              <button
                onClick={() => saveMut.mutate(current)}
                disabled={saveMut.isPending}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-md bg-brand-600 text-white hover:bg-brand-700 text-sm font-semibold disabled:opacity-50"
              >
                <Check className="w-4 h-4" />
                {saveMut.isPending ? "Saving..." : "Add to quiz"}
              </button>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
