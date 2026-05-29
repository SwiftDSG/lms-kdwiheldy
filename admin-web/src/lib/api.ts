import axios from "axios";
import type {
  CreateOptionForm,
  CreateQuestionForm,
  CreateQuizForm,
  Question,
  Quiz,
  QuizSession,
} from "@/types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:3000";

const client = axios.create({ baseURL: `${BASE_URL}/api/v1` });

// Attach JWT from localStorage on every request
client.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("admin_token");
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function login(email: string, password: string): Promise<string> {
  const { data } = await client.post<{ token: string }>("/auth/login", {
    email,
    password,
  });
  return data.token;
}

// ── Quizzes ───────────────────────────────────────────────────────────────────

export async function getQuizzes(): Promise<Quiz[]> {
  const { data } = await client.get<Quiz[]>("/admin/quizzes");
  return data;
}

export async function createQuiz(body: CreateQuizForm): Promise<Quiz> {
  const { data } = await client.post<Quiz>("/admin/quizzes", body);
  return data;
}

export async function updateQuiz(
  id: string,
  body: Partial<CreateQuizForm>
): Promise<Quiz> {
  const { data } = await client.put<Quiz>(`/admin/quizzes/${id}`, body);
  return data;
}

export async function deleteQuiz(id: string): Promise<void> {
  await client.delete(`/admin/quizzes/${id}`);
}

export async function togglePublish(id: string): Promise<Quiz> {
  const { data } = await client.post<Quiz>(`/admin/quizzes/${id}/publish`);
  return data;
}

// ── Questions ─────────────────────────────────────────────────────────────────

export async function getQuestion(id: string): Promise<Question> {
  const { data } = await client.get<Question>(`/admin/questions/${id}`);
  return data;
}

export async function getQuestions(quizId?: string): Promise<Question[]> {
  const { data } = await client.get<Question[]>("/admin/questions", {
    params: quizId ? { quiz_id: quizId } : undefined,
  });
  return data;
}

export async function createQuestion(
  body: CreateQuestionForm
): Promise<{ question: Question; options: CreateOptionForm[] }> {
  const { data } = await client.post("/admin/questions", body);
  return data;
}

export async function updateQuestion(
  id: string,
  body: Partial<CreateQuestionForm>
): Promise<{ question: Question; options: CreateOptionForm[] }> {
  const { data } = await client.put(`/admin/questions/${id}`, body);
  return data;
}

export async function deleteQuestion(id: string): Promise<void> {
  await client.delete(`/admin/questions/${id}`);
}

export async function bulkImport(payload: unknown): Promise<{
  quiz_id: string;
  questions_imported: number;
}> {
  const { data } = await client.post("/admin/questions/bulk", payload);
  return data;
}

// ── Image Upload ──────────────────────────────────────────────────────────────

export async function uploadImage(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await client.post<{ url: string }>(
    "/admin/upload/image",
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return data.url;
}

// ── Sessions ──────────────────────────────────────────────────────────────────

export async function getSessions(): Promise<QuizSession[]> {
  const { data } = await client.get<QuizSession[]>("/admin/sessions");
  return data;
}
