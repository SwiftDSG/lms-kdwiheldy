"use client";

import { useFieldArray, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Plus, Trash2, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import { uploadImage } from "@/lib/api";
import toast from "react-hot-toast";
import type { Question, QuestionSubtype } from "@/types";
import MathText from "./MathText";

const TWK_SUBTYPES = [
  { value: "PANCASILA",           label: "Pancasila" },
  { value: "UUD_1945",            label: "UUD 1945" },
  { value: "BHINNEKA",            label: "Bhinneka Tunggal Ika" },
  { value: "NKRI",                label: "NKRI" },
  { value: "SEJARAH_NASIONAL",    label: "Sejarah Nasional" },
  { value: "SISTEM_PEMERINTAHAN", label: "Sistem Pemerintahan" },
  { value: "BELA_NEGARA",         label: "Bela Negara" },
  { value: "BAHASA_INDONESIA",    label: "Bahasa Indonesia" },
] as const;

const TIU_SUBTYPES = [
  { value: "ANALOGI_VERBAL",           label: "Analogi Verbal" },
  { value: "ANALOGI_GAMBAR",           label: "Analogi Gambar" },
  { value: "SILOGISME",                label: "Silogisme" },
  { value: "ANTONIM",                  label: "Antonim" },
  { value: "SINONIM",                  label: "Sinonim" },
  { value: "ARITMATIKA",               label: "Aritmatika" },
  { value: "DERET_ANGKA",              label: "Deret Angka" },
  { value: "SOAL_CERITA",              label: "Soal Cerita" },
  { value: "PERBANDINGAN_KUANTITATIF", label: "Perbandingan Kuantitatif" },
] as const;

const TKP_SUBTYPES = [
  { value: "PELAYANAN_PUBLIK",    label: "Pelayanan Publik" },
  { value: "PROFESIONALISME",     label: "Profesionalisme" },
  { value: "JEJARING_KERJA",      label: "Jejaring Kerja" },
  { value: "SOSIAL_BUDAYA",       label: "Sosial Budaya" },
  { value: "TEKNOLOGI_INFORMASI", label: "Teknologi Informasi" },
  { value: "ORIENTASI_BELAJAR",   label: "Orientasi Belajar" },
  { value: "MENGENDALIKAN_DIRI",  label: "Mengendalikan Diri" },
  { value: "BERADAPTASI",         label: "Beradaptasi" },
  { value: "KREATIVITAS_INOVASI", label: "Kreativitas & Inovasi" },
] as const;

const ALL_SUBTYPES = [...TWK_SUBTYPES, ...TIU_SUBTYPES, ...TKP_SUBTYPES];

const SUBTYPE_VALUES = [
  ...TWK_SUBTYPES.map((s) => s.value),
  ...TIU_SUBTYPES.map((s) => s.value),
  ...TKP_SUBTYPES.map((s) => s.value),
] as [QuestionSubtype, ...QuestionSubtype[]];

function subtypesForCategory(cat?: string) {
  if (cat === "TWK") return [...TWK_SUBTYPES];
  if (cat === "TIU") return [...TIU_SUBTYPES];
  if (cat === "TKP") return [...TKP_SUBTYPES];
  return [...ALL_SUBTYPES];
}

const optionSchema = z.object({
  label: z.string().min(1),
  content: z.string().min(1, "Option content required"),
  score: z.coerce.number().int().min(0).max(5),
});

const schema = z.object({
  type: z.enum(["MCQ", "TRUE_FALSE", "ESSAY", "IMAGE"]),
  subtype: z.enum(SUBTYPE_VALUES, { message: "Subtype is required" }),
  content: z.string().min(1, "Question text is required"),
  image_url: z.string().optional(),
  explanation: z.string().optional(),
  position: z.coerce.number().int().min(1),
  // Options are only validated when the type requires them (MCQ/TRUE_FALSE).
  // For ESSAY/IMAGE the array will be empty so no items are validated.
  options: z.array(optionSchema).optional(),
});

type QuestionFormData = z.infer<typeof schema>;

interface Props {
  defaultValues?: Partial<Question>;
  quizId: string;
  onSubmit: (data: QuestionFormData & { quiz_id: string }) => Promise<unknown>;
  isLoading?: boolean;
  submitLabel?: string;
  category?: string; // 'TWK' | 'TIU' | 'TKP'
}

const MCQ_DEFAULTS = ["A", "B", "C", "D", "E"].map((l) => ({
  label: l,
  content: "",
  score: 0,
}));

const TRUE_FALSE_DEFAULTS = [
  { label: "A", content: "Benar", score: 0 },
  { label: "B", content: "Salah", score: 0 },
];

export default function QuestionEditor({
  defaultValues,
  quizId,
  onSubmit,
  isLoading,
  submitLabel = "Save",
  category,
}: Props) {
  const [uploading, setUploading] = useState(false);

  const {
    register,
    control,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<QuestionFormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      type: defaultValues?.type ?? "MCQ",
      subtype: defaultValues?.subtype ?? undefined,
      content: defaultValues?.content ?? "",
      image_url: defaultValues?.image_url ?? "",
      explanation: defaultValues?.explanation ?? "",
      position: defaultValues?.position ?? 1,
      options: (() => {
        if (defaultValues?.options?.length) {
          return defaultValues.options.map((o) => ({
            label: o.label,
            content: o.content,
            score: o.score,
          }));
        }
        const t = defaultValues?.type ?? "MCQ";
        if (t === "TRUE_FALSE") return TRUE_FALSE_DEFAULTS;
        if (t === "ESSAY" || t === "IMAGE") return [];
        return MCQ_DEFAULTS;
      })(),
    },
  });

  const { fields, append, remove, replace } = useFieldArray({
    control,
    name: "options",
  });
  const questionType = watch("type");
  const isTKP = category === "TKP";

  // Reset options when question type changes.
  // prevTypeRef prevents the reset from firing on initial mount (important for the
  // edit page, where defaultValues already have the correct options).
  const prevTypeRef = useRef(questionType);
  useEffect(() => {
    if (prevTypeRef.current === questionType) return;
    prevTypeRef.current = questionType;

    if (questionType === "TRUE_FALSE") {
      replace(TRUE_FALSE_DEFAULTS);
    } else if (questionType === "MCQ") {
      replace(MCQ_DEFAULTS);
    } else {
      // ESSAY / IMAGE — no options needed; clearing prevents stale options
      // from failing Zod validation on submit.
      replace([]);
    }
  }, [questionType, replace]);

  // Image drop upload
  const onDrop = useCallback(
    async (files: File[]) => {
      const file = files[0];
      if (!file) return;
      setUploading(true);
      try {
        const url = await uploadImage(file);
        setValue("image_url", url);
        toast.success("Image uploaded");
      } catch {
        toast.error("Image upload failed");
      } finally {
        setUploading(false);
      }
    },
    [setValue]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "image/*": [] },
    maxFiles: 1,
  });

  const handleFormSubmit = async (data: QuestionFormData) => {
    await onSubmit({
      ...data,
      quiz_id: quizId,
      image_url: data.image_url || undefined,
      explanation: data.explanation || undefined,
    });
  };

  const allOptions = watch("options") ?? [];

  const markCorrect = (correctIndex: number) => {
    fields.forEach((_, j) => {
      setValue(`options.${j}.score`, j === correctIndex ? 5 : 0);
    });
  };

  const addOption = () => {
    const nextLabel = String.fromCharCode(65 + fields.length); // A=65
    append({ label: nextLabel, content: "", score: 0 });
  };

  return (
    <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-5">
      {/* Type */}
      <div>
        <label className="block text-sm font-medium mb-1">Question Type *</label>
        <select
          {...register("type")}
          className="w-full border-3 border-brand-600 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
        >
          <option value="MCQ">Multiple Choice (MCQ)</option>
          <option value="TRUE_FALSE">True / False</option>
          <option value="ESSAY">Essay / Open-ended</option>
          <option value="IMAGE">Image-based</option>
        </select>
      </div>

      {/* Subtype */}
      <div>
        <label className="block text-sm font-medium mb-1">Subtype *</label>
        <select
          {...register("subtype")}
          className="w-full border-3 border-brand-600 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
        >
          <option value="">— select subtype —</option>
          {subtypesForCategory(category).map((s) => (
            <option key={s.value} value={s.value}>{s.label}</option>
          ))}
        </select>
        {errors.subtype && (
          <p className="text-red-500 text-xs mt-1">{errors.subtype.message}</p>
        )}
      </div>

      {/* Question content */}
      <div>
        <label className="block text-sm font-medium mb-1">Question Text *</label>
        <textarea
          {...register("content")}
          rows={4}
          className="w-full border-3 border-brand-600 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
          placeholder="Type the question here... supports LaTeX math: $x^2$ or $$\frac{a}{b}$$"
        />
        {errors.content && (
          <p className="text-red-500 text-xs mt-1">{errors.content.message}</p>
        )}
        {watch("content") && (
          <div className="mt-2 p-3 bg-gray-50 rounded-xl border-3 border-brand-600 text-sm">
            <p className="text-xs text-gray-400 mb-1">Preview</p>
            <MathText text={watch("content")} />
          </div>
        )}
      </div>

      {/* Image upload (for IMAGE type or supplementary) */}
      {(questionType === "IMAGE" || questionType === "MCQ") && (
        <div>
          <label className="block text-sm font-medium mb-1">
            {questionType === "IMAGE" ? "Question Image *" : "Image (optional)"}
          </label>
          <div
            {...getRootProps()}
            className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors ${
              isDragActive
                ? "border-brand-500 bg-brand-50"
                : "border-brand-300 hover:border-brand-500"
            }`}
          >
            <input {...getInputProps()} />
            <Upload className="w-8 h-8 mx-auto mb-2 text-gray-400" />
            <p className="text-sm text-gray-500">
              {uploading
                ? "Uploading..."
                : "Drop an image here, or click to select"}
            </p>
          </div>
          {watch("image_url") && (
            <div className="mt-2">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={watch("image_url")}
                alt="Question"
                className="max-h-48 rounded-xl border-3 border-brand-600"
              />
              <input type="hidden" {...register("image_url")} />
            </div>
          )}
        </div>
      )}

      {/* Options (IMAGE) — image URL per option */}
      {questionType === "IMAGE" && (
        <div>
          <label className="block text-sm font-medium mb-2">Answer Options (image URLs)</label>
          <div className="space-y-2">
            {fields.map((field, i) => (
              <div key={field.id} className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="w-6 text-sm font-mono text-gray-500 shrink-0">{field.label}</span>
                  <input
                    {...register(`options.${i}.content`)}
                    className="flex-1 border-3 border-brand-600 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
                    placeholder="https://..."
                  />
                  <label className="flex items-center gap-1 shrink-0 cursor-pointer">
                    <input
                      type="radio"
                      name="correct_option_img"
                      className="accent-green-600"
                      checked={allOptions[i]?.score === 5}
                      onChange={() => markCorrect(i)}
                    />
                    <span className="text-xs text-gray-500">Correct</span>
                  </label>
                </div>
                {watch(`options.${i}.content`)?.startsWith("http") && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={watch(`options.${i}.content`)}
                    alt={`Option ${field.label}`}
                    className="ml-8 max-h-24 rounded-lg border-3 border-brand-600"
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Options (MCQ / TRUE_FALSE) */}
      {(questionType === "MCQ" || questionType === "TRUE_FALSE") && (
        <div>
          <label className="block text-sm font-medium mb-2">
            Answer Options *{" "}
            {isTKP && (
              <span className="text-gray-400 font-normal text-xs">
                (TKP: set score 1–5 for each option)
              </span>
            )}
          </label>
          <div className="space-y-2">
            {fields.map((field, i) => (
              <div key={field.id} className="flex items-center gap-2">
                <span className="w-6 text-sm font-mono text-gray-500 shrink-0">
                  {field.label}
                </span>
                <input
                  {...register(`options.${i}.content`)}
                  className="flex-1 border-3 border-brand-600 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
                  placeholder={`Option ${field.label}`}
                />
                {errors.options?.[i]?.content && (
                  <span className="text-red-500 text-xs shrink-0">
                    {errors.options[i]?.content?.message}
                  </span>
                )}
                {/* Score (TKP) or correct toggle (MCQ/TF) */}
                {isTKP ? (
                  <div className="flex items-center gap-1 shrink-0">
                    <span className="text-xs text-gray-500">Score</span>
                    <input
                      {...register(`options.${i}.score`)}
                      type="number"
                      min={1}
                      max={5}
                      className="w-12 border-3 border-brand-600 rounded px-2 py-1 text-sm text-center focus:outline-none"
                    />
                  </div>
                ) : (
                  <label className="flex items-center gap-1 shrink-0 cursor-pointer">
                    <input
                      type="radio"
                      name="correct_option"
                      className="accent-green-600"
                      checked={allOptions[i]?.score === 5}
                      onChange={() => markCorrect(i)}
                    />
                    <span className="text-xs text-gray-500">Correct</span>
                  </label>
                )}
                {questionType === "MCQ" && fields.length > 2 && (
                  <button
                    type="button"
                    onClick={() => remove(i)}
                    className="p-1 border-3 border-danger rounded-md text-danger hover:bg-red-50"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            ))}
          </div>
          {questionType === "MCQ" && fields.length < 7 && (
            <button
              type="button"
              onClick={addOption}
              className="mt-2 flex items-center gap-1.5 text-sm text-brand-600 hover:text-brand-700"
            >
              <Plus className="w-4 h-4" /> Add option
            </button>
          )}
        </div>
      )}

      {/* Explanation */}
      <div>
        <label className="block text-sm font-medium mb-1">
          Explanation (shown after answering)
        </label>
        <textarea
          {...register("explanation")}
          rows={2}
          className="w-full border-3 border-brand-600 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
          placeholder="Optional explanation for the correct answer..."
        />
        {watch("explanation") && (
          <div className="mt-2 p-3 bg-gray-50 rounded-xl border-3 border-brand-600 text-sm">
            <p className="text-xs text-gray-400 mb-1">Preview</p>
            <MathText text={watch("explanation")!} />
          </div>
        )}
      </div>

      {/* Position */}
      <div>
        <label className="block text-sm font-medium mb-1">Position *</label>
        <input
          {...register("position")}
          type="number"
          min={1}
          className="w-24 border-3 border-brand-600 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
        />
      </div>

      <button
        type="submit"
        disabled={isLoading || uploading}
        className="bg-brand-600 text-white px-5 py-2 rounded-md text-sm font-semibold hover:bg-brand-700 disabled:opacity-50 transition-colors"
      >
        {isLoading ? "Saving..." : submitLabel}
      </button>
    </form>
  );
}
