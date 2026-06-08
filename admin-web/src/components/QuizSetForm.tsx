"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import type { Quiz } from "@/types";

const schema = z.object({
  title: z.string().min(1, "Title is required"),
  description: z.string().optional(),
  category: z.enum(["TWK", "TIU", "TKP", "MIXED"]),
  time_limit: z.preprocess(
    (v) => (v === "" || v === undefined || v === null ? undefined : Number(v)),
    z.number().int().positive().optional()
  ),
});

type FormData = z.infer<typeof schema>;

interface Props {
  defaultValues?: Partial<Quiz>;
  onSubmit: (data: FormData) => Promise<unknown>;
  isLoading?: boolean;
  submitLabel?: string;
}

export default function QuizSetForm({
  defaultValues,
  onSubmit,
  isLoading,
  submitLabel = "Save",
}: Props) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      title: defaultValues?.title ?? "",
      description: defaultValues?.description ?? "",
      category: defaultValues?.category ?? "TWK",
      time_limit: defaultValues?.time_limit ?? undefined,
    },
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
      <div>
        <label className="block text-sm font-medium mb-1">Title *</label>
        <input
          {...register("title")}
          className="w-full border-3 border-brand-600 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
          placeholder="e.g. TWK Latihan Soal #1"
        />
        {errors.title && (
          <p className="text-red-500 text-xs mt-1">{errors.title.message}</p>
        )}
      </div>

      <div>
        <label className="block text-sm font-medium mb-1">Description</label>
        <textarea
          {...register("description")}
          rows={3}
          className="w-full border-3 border-brand-600 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
          placeholder="Optional description..."
        />
      </div>

      <div>
        <label className="block text-sm font-medium mb-1">Category *</label>
        <select
          {...register("category")}
          className="w-full border-3 border-brand-600 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
        >
          <option value="TWK">TWK — Tes Wawasan Kebangsaan</option>
          <option value="TIU">TIU — Tes Intelejensi Umum</option>
          <option value="TKP">TKP — Tes Karakteristik Pribadi</option>
          <option value="MIXED">Mixed (All categories)</option>
        </select>
      </div>

      <div>
        <label className="block text-sm font-medium mb-1">
          Time Limit (minutes)
        </label>
        <input
          {...register("time_limit")}
          type="number"
          min={1}
          className="w-full border-3 border-brand-600 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400"
          placeholder="Leave blank for no limit"
        />
      </div>

      <button
        type="submit"
        disabled={isLoading}
        className="bg-brand-600 text-white px-5 py-2 rounded-md text-sm font-semibold hover:bg-brand-700 disabled:opacity-50 transition-colors"
      >
        {isLoading ? "Saving..." : submitLabel}
      </button>
    </form>
  );
}
