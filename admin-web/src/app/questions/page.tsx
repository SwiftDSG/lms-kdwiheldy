"use client";

import { useQuery } from "@tanstack/react-query";
import { getQuestions, getQuizSets } from "@/lib/api";
import Link from "next/link";
import { useState } from "react";

export default function QuestionBankPage() {
  const [selectedSetId, setSelectedSetId] = useState<string>("");

  const { data: quizSets = [] } = useQuery({
    queryKey: ["quiz-sets"],
    queryFn: getQuizSets,
  });

  const { data: questions = [], isLoading } = useQuery({
    queryKey: ["questions", selectedSetId || "all"],
    queryFn: () => getQuestions(selectedSetId || undefined),
  });

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Question Bank</h1>

      <div className="flex items-center gap-3 mb-4">
        <select
          value={selectedSetId}
          onChange={(e) => setSelectedSetId(e.target.value)}
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="">All Quiz Sets</option>
          {quizSets.map((qs) => (
            <option key={qs.id} value={qs.id}>
              {qs.title}
            </option>
          ))}
        </select>
        <span className="text-sm text-gray-500">{questions.length} questions</span>
      </div>

      {isLoading ? (
        <p className="text-gray-400">Loading...</p>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-gray-500 text-left">
              <tr>
                <th className="px-4 py-3 font-medium">#</th>
                <th className="px-4 py-3 font-medium">Question</th>
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">Options</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {questions.map((q, i) => {
                const quizSet = quizSets.find((qs) => qs.id === q.quiz_set_id);
                return (
                  <tr key={q.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-gray-400 font-mono text-xs">
                      {i + 1}
                    </td>
                    <td className="px-4 py-3 max-w-xs">
                      <p className="line-clamp-2 font-medium">{q.content}</p>
                      {quizSet && (
                        <p className="text-xs text-gray-400 mt-0.5">
                          {quizSet.title}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 bg-gray-100 rounded text-xs">
                        {q.type}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-500">
                      {q.options?.length ?? 0}
                    </td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/quiz-sets/${q.quiz_set_id}/questions/${q.id}`}
                        className="text-brand-600 hover:text-brand-700 text-sm"
                      >
                        Edit
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {questions.length === 0 && (
            <p className="text-center text-gray-400 py-12 text-sm">
              No questions found.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
