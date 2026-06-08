"use client";

import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  createQuestion,
  generateQuestion,
  generateAnalogiQuestion,
  getQuizzes,
  getQuestions,
} from "@/lib/api";
import type {
  GeneratedQuestion,
  QuestionSubtype,
  Category,
} from "@/types";
import { ArrowLeft, Check, X, Wand2, ImageIcon } from "lucide-react";
import MathText from "@/components/MathText";
import Link from "next/link";
import toast from "react-hot-toast";

// ── Subtype catalogue ─────────────────────────────────────────────────────────

const SUBTYPES_BY_CATEGORY: Record<string, QuestionSubtype[]> = {
  TWK: [
    "PANCASILA", "UUD_1945", "BHINNEKA", "NKRI",
    "SEJARAH_NASIONAL", "SISTEM_PEMERINTAHAN", "BELA_NEGARA", "BAHASA_INDONESIA",
  ],
  TIU: [
    "ANALOGI_VERBAL", "ANALOGI_GAMBAR", "SILOGISME", "ANTONIM", "SINONIM",
    "ARITMATIKA", "DERET_ANGKA", "SOAL_CERITA", "PERBANDINGAN_KUANTITATIF",
  ],
  TKP: [
    "PELAYANAN_PUBLIK", "PROFESIONALISME", "JEJARING_KERJA", "SOSIAL_BUDAYA",
    "TEKNOLOGI_INFORMASI", "ORIENTASI_BELAJAR", "MENGENDALIKAN_DIRI",
    "BERADAPTASI", "KREATIVITAS_INOVASI",
  ],
};

function subtypesForCategory(category: Category | undefined): QuestionSubtype[] {
  if (!category || category === "MIXED") {
    return [
      ...SUBTYPES_BY_CATEGORY.TWK,
      ...SUBTYPES_BY_CATEGORY.TIU,
      ...SUBTYPES_BY_CATEGORY.TKP,
    ];
  }
  return SUBTYPES_BY_CATEGORY[category] ?? [];
}

function subtypeLabel(s: QuestionSubtype): string {
  return s.replace(/_/g, " ");
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function GeneratePage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();

  const [selectedSubtype, setSelectedSubtype] = useState<QuestionSubtype | null>(null);
  const [current, setCurrent] = useState<GeneratedQuestion | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);
  const [addedCount, setAddedCount] = useState(0);

  const { data: quizzes = [] } = useQuery({
    queryKey: ["quizzes"],
    queryFn: getQuizzes,
  });
  const quiz = quizzes.find((q) => q.id === id);

  // Fetch ALL questions across all quizzes so we can find seeds for any subtype,
  // even if the current quiz doesn't have any yet.
  const { data: allQuestions = [] } = useQuery({
    queryKey: ["questions"],
    queryFn: () => getQuestions(),
  });

  const subtypes = subtypesForCategory(quiz?.category);

  const saveMut = useMutation({
    mutationFn: (q: GeneratedQuestion) =>
      createQuestion({
        quiz_id:     id,
        type:        selectedSubtype === "ANALOGI_GAMBAR" ? "IMAGE" : "MCQ",
        subtype:     selectedSubtype ?? "SILOGISME",
        content:     q.content,
        image_url:   q.image_url,
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
      fetchNext(selectedSubtype!);
    },
    onError: () => toast.error("Failed to save question"),
  });

  const fetchNext = async (subtype: QuestionSubtype) => {
    setIsGenerating(true);
    setGenError(null);
    setCurrent(null);
    try {
      if (subtype === "ANALOGI_GAMBAR") {
        const result = await generateAnalogiQuestion();
        setCurrent(result.question);
      } else {
        // Pick a random seed question of this subtype from any quiz in the DB
        const pool = allQuestions.filter((q) => q.subtype === subtype);
        if (pool.length === 0) {
          setGenError(`No existing ${subtypeLabel(subtype)} questions to use as reference. Add at least one first.`);
          setIsGenerating(false);
          return;
        }
        const seed = pool[Math.floor(Math.random() * pool.length)];
        const result = await generateQuestion(seed.id);
        setCurrent(result.question);
      }
    } catch (e: unknown) {
      const msg =
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Generation failed";
      setGenError(msg);
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSubtypeClick = (subtype: QuestionSubtype) => {
    setSelectedSubtype(subtype);
    setCurrent(null);
    setGenError(null);
    fetchNext(subtype);
  };

  const isAnalogiGambar = selectedSubtype === "ANALOGI_GAMBAR";

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
        <h1 className="text-xl font-bold flex-1">Generate Questions</h1>
        {addedCount > 0 && (
          <span className="text-sm text-success font-semibold">
            {addedCount} added
          </span>
        )}
      </div>

      {/* Subtype picker */}
      <div className="mb-6">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
          Select subtype
        </p>
        <div className="flex flex-wrap gap-2">
          {subtypes.map((s) => (
            <button
              key={s}
              onClick={() => handleSubtypeClick(s)}
              disabled={isGenerating}
              className={`px-3 py-1.5 rounded-full text-xs font-semibold border-2 transition-colors disabled:opacity-50 ${
                selectedSubtype === s
                  ? "bg-brand-600 text-white border-brand-600"
                  : "border-brand-300 text-brand-600 hover:bg-brand-50"
              }`}
            >
              {subtypeLabel(s)}
            </button>
          ))}
        </div>
      </div>

      {/* Generated question card */}
      {selectedSubtype && (
        <div className="bg-white rounded-xl border-3 border-brand-600 p-6 min-h-52 flex flex-col">
          {isGenerating ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-3 text-gray-400">
              <Wand2 className="w-8 h-8 animate-pulse" />
              <p className="text-sm">Generating {subtypeLabel(selectedSubtype)} question…</p>
            </div>
          ) : genError ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-3">
              <p className="text-sm text-red-500">{genError}</p>
              <button
                onClick={() => fetchNext(selectedSubtype)}
                className="text-sm text-brand-600 hover:underline"
              >
                Try again
              </button>
            </div>
          ) : current ? (
            <>
              {/* Question image (analogi gambar) */}
              {current.image_url && (
                <div className="mb-4">
                  <div className="flex items-center gap-1.5 text-xs text-gray-400 font-medium uppercase tracking-wide mb-2">
                    <ImageIcon className="w-3.5 h-3.5" />
                    Question image
                  </div>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={current.image_url}
                    alt="Analogi question"
                    className="rounded-lg border border-gray-200 max-w-full"
                  />
                </div>
              )}

              {/* Question content */}
              <p className="text-sm font-medium mb-4">
                <MathText text={current.content} />
              </p>

              {/* Options */}
              <div className={`mb-6 ${isAnalogiGambar ? "grid grid-cols-3 gap-2" : "space-y-1.5"}`}>
                {current.options.map((o) =>
                  isAnalogiGambar ? (
                    /* Analogi: options are image URLs */
                    <div
                      key={o.label}
                      className={`relative rounded-lg border-2 overflow-hidden ${
                        o.score === 5 ? "border-green-400" : "border-gray-200"
                      }`}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={o.content}
                        alt={`Option ${o.label}`}
                        className="w-full object-cover"
                      />
                      <div
                        className={`absolute top-1 left-1 text-xs font-bold w-5 h-5 flex items-center justify-center rounded-full ${
                          o.score === 5
                            ? "bg-green-500 text-white"
                            : "bg-white/80 text-gray-600"
                        }`}
                      >
                        {o.label}
                      </div>
                    </div>
                  ) : (
                    /* Regular: options are text */
                    <div
                      key={o.label}
                      className={`flex items-center gap-2 text-sm px-3 py-1.5 rounded-md border ${
                        o.score === 5
                          ? "bg-green-50 border-green-300 text-green-700 font-semibold"
                          : "border-transparent text-gray-600"
                      }`}
                    >
                      <span className="font-mono text-xs w-4 shrink-0">{o.label}.</span>
                      <span className="flex-1"><MathText text={o.content} /></span>
                      {o.score === 5 && <Check className="w-3.5 h-3.5 shrink-0" />}
                    </div>
                  )
                )}
              </div>

              {/* Explanation */}
              {current.explanation && (
                <div className="mb-4 border-t border-gray-100 pt-4 space-y-2">
                  <div>
                    <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1">
                      Explanation
                    </p>
                    <p className="text-sm text-gray-700">
                      <MathText text={current.explanation} />
                    </p>
                  </div>
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

              {/* Actions */}
              <div className="flex gap-3 mt-auto">
                <button
                  onClick={() => fetchNext(selectedSubtype)}
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
                  {saveMut.isPending ? "Saving…" : "Add to quiz"}
                </button>
              </div>
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}
