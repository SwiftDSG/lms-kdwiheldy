export type Category = "TWK" | "TIU" | "TKP" | "MIXED";
export type QuestionType = "MCQ" | "TRUE_FALSE" | "ESSAY" | "IMAGE";

export interface Quiz {
  id: string;
  title: string;
  description: string | null;
  category: Category;
  time_limit: number | null;
  is_published: boolean;
  created_at: string;
  updated_at: string;
}

export interface QuestionOption {
  id: string;
  question_id: string;
  label: string;
  content: string;
  score: number;
  is_correct: boolean;
}

export interface Question {
  id: string;
  quiz_id: string;
  type: QuestionType;
  content: string;
  image_url: string | null;
  explanation: string | null;
  position: number;
  created_at: string;
  options: QuestionOption[];
}

export interface QuizSession {
  id: string;
  quiz_id: string;
  device_id: string;
  started_at: string;
  completed_at: string | null;
  score: number | null;
  synced_at: string;
}

// ── Form types ────────────────────────────────────────────────────────────────

export interface CreateQuizForm {
  title: string;
  description?: string;
  category: Category;
  time_limit?: number;
}

export interface CreateOptionForm {
  label: string;
  content: string;
  score: number;
  is_correct: boolean;
}

export interface CreateQuestionForm {
  quiz_id: string;
  type: QuestionType;
  content: string;
  image_url?: string;
  explanation?: string;
  position: number;
  options?: CreateOptionForm[];
}
