"use client";

import { useFieldArray, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Plus, Trash2, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useDropzone } from "react-dropzone";
import { uploadImage } from "@/lib/api";
import toast from "react-hot-toast";
import type { Question } from "@/types";
import MathText from "./MathText";

const optionSchema = z.object({
  label: z.string().min(1),
  content: z.string().min(1, "Option content required"),
  score: z.coerce.number().int().min(0).max(5),
  is_correct: z.boolean(),
});

const schema = z.object({
  type: z.enum(["MCQ", "TRUE_FALSE", "ESSAY", "IMAGE"]),
  content: z.string().min(1, "Question text is required"),
  image_url: z.string().optional(),
  explanation: z.string().optional(),
  position: z.coerce.number().int().min(1),
  // Options are only validated when the type requires them (MCQ/TRUE_FALSE).
  // For ESSAY/IMAGE the array will be empty so no items are validated.
  options: z.array(optionSchema).optional(),
});

type FormData = z.infer<typeof schema>;

interface Props {
  defaultValues?: Partial<Question>;
  quizId: string;
  onSubmit: (data: FormData & { quiz_id: string }) => Promise<unknown>;
  isLoading?: boolean;
  submitLabel?: string;
  category?: string; // 'TWK' | 'TIU' | 'TKP'
}

const MCQ_DEFAULTS = ["A", "B", "C", "D", "E"].map((l) => ({
  label: l,
  content: "",
  score: 0,
  is_correct: false,
}));

const TRUE_FALSE_DEFAULTS = [
  { label: "A", content: "Benar", score: 0, is_correct: false },
  { label: "B", content: "Salah", score: 0, is_correct: false },
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
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      type: defaultValues?.type ?? "MCQ",
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
            is_correct: o.is_correct,
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

  const handleFormSubmit = async (data: FormData) => {
    await onSubmit({
      ...data,
      quiz_id: quizId,
      image_url: data.image_url || undefined,
      explanation: data.explanation || undefined,
    });
  };

  const addOption = () => {
    const nextLabel = String.fromCharCode(65 + fields.length); // A=65
    append({ label: nextLabel, content: "", score: 0, is_correct: false });
  };

  return (
    <form onSubmit={handleSubmit(handleFormSubmit)} className="space-y-5">
      {/* Type */}
      <div>
        <label className="block text-sm font-medium mb-1">Question Type *</label>
        <select
          {...register("type")}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="MCQ">Multiple Choice (MCQ)</option>
          <option value="TRUE_FALSE">True / False</option>
          <option value="ESSAY">Essay / Open-ended</option>
          <option value="IMAGE">Image-based</option>
        </select>
      </div>

      {/* Question content */}
      <div>
        <label className="block text-sm font-medium mb-1">Question Text *</label>
        <textarea
          {...register("content")}
          rows={4}
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          placeholder="Type the question here... supports LaTeX math: $x^2$ or $$\frac{a}{b}$$"
        />
        {errors.content && (
          <p className="text-red-500 text-xs mt-1">{errors.content.message}</p>
        )}
        {watch("content") && (
          <div className="mt-2 p-3 bg-gray-50 rounded-lg border border-gray-200 text-sm">
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
            className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
              isDragActive
                ? "border-brand-500 bg-brand-50"
                : "border-gray-300 hover:border-gray-400"
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
                className="max-h-48 rounded-lg border border-gray-200"
              />
              <input type="hidden" {...register("image_url")} />
            </div>
          )}
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
                  className="flex-1 border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
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
                      className="w-12 border border-gray-300 rounded px-2 py-1 text-sm text-center focus:outline-none"
                    />
                  </div>
                ) : (
                  <label className="flex items-center gap-1 shrink-0 cursor-pointer">
                    <input
                      type="checkbox"
                      className="accent-green-600"
                      {...register(`options.${i}.is_correct`)}
                      onChange={(e) => {
                        // Checking "Correct" also sets score=5 (server uses score for points).
                        setValue(`options.${i}.is_correct`, e.target.checked);
                        setValue(`options.${i}.score`, e.target.checked ? 5 : 0);
                      }}
                    />
                    <span className="text-xs text-gray-500">Correct</span>
                  </label>
                )}
                {questionType === "MCQ" && fields.length > 2 && (
                  <button
                    type="button"
                    onClick={() => remove(i)}
                    className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-600"
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
          className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
          placeholder="Optional explanation for the correct answer..."
        />
      </div>

      {/* Position */}
      <div>
        <label className="block text-sm font-medium mb-1">Position *</label>
        <input
          {...register("position")}
          type="number"
          min={1}
          className="w-24 border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        />
      </div>

      <button
        type="submit"
        disabled={isLoading || uploading}
        className="bg-brand-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-brand-700 disabled:opacity-50 transition-colors"
      >
        {isLoading ? "Saving..." : submitLabel}
      </button>
    </form>
  );
}
